from unittest.mock import patch

from fastapi.testclient import TestClient

from chorba.cmd.server import create_app
from chorba.lib.markup import _schema_org


def test_parses_basic_ingredient_fields():
    recipe = _schema_org.Recipe(
        {
            "name": "Test",
            "recipeIngredient": ["3 pounds pork shoulder, cut into 2-inch chunks"],
        }
    )

    ingredient = recipe.ingredients[0]

    assert ingredient == _schema_org.Ingredient(
        id="ingredient_0",
        sentence="3 pounds pork shoulder, cut into 2-inch chunks",
        names=["pork shoulder"],
        amounts=[
            _schema_org.IngredientAmount(
                quantity="3",
                quantity_max="3",
                unit="pounds",
                text="3 pounds",
            )
        ],
        size=None,
        preparation="cut into 2 inch chunks",
        comment=None,
        purpose=None,
    )


def test_parses_ranged_amounts_and_names():
    ingredient = _schema_org.Recipe(
        {"name": "Test", "recipeIngredient": ["1-2 cloves garlic, minced"]}
    ).ingredients[0]

    assert ingredient == _schema_org.Ingredient(
        id="ingredient_0",
        sentence="1-2 cloves garlic, minced",
        names=["garlic"],
        amounts=[
            _schema_org.IngredientAmount(
                quantity="1",
                quantity_max="2",
                unit="clove",
                text="1-2 clove",
            )
        ],
        size=None,
        preparation="minced",
        comment=None,
        purpose=None,
    )


def test_flattens_composite_amounts():
    ingredient = _schema_org.Recipe(
        {"name": "Test", "recipeIngredient": ["1 cup plus 1 tablespoon olive oil"]}
    ).ingredients[0]

    assert ingredient == _schema_org.Ingredient(
        id="ingredient_0",
        sentence="1 cup plus 1 tablespoon olive oil",
        names=["olive oil"],
        amounts=[
            _schema_org.IngredientAmount(
                quantity="1",
                quantity_max="1",
                unit="cup",
                text="1 cup",
            ),
            _schema_org.IngredientAmount(
                quantity="1",
                quantity_max="1",
                unit="tablespoon",
                text="1 tablespoon",
            ),
        ],
        size=None,
        preparation=None,
        comment=None,
        purpose=None,
    )


def test_falls_back_when_parser_raises():
    with patch.object(
        _schema_org,
        "_parse_ingredient_sentence",
        side_effect=RuntimeError("boom"),
    ):
        ingredient = _schema_org.Recipe(
            {"name": "Test", "recipeIngredient": ["mystery ingredient"]}
        ).ingredients[0]

    assert ingredient == _schema_org.Ingredient(
        id="ingredient_0",
        sentence="mystery ingredient",
        names=[],
        amounts=[],
        size=None,
        preparation=None,
        comment=None,
        purpose=None,
    )


def test_directions_include_linked_highlights():
    recipe = _schema_org.Recipe(
        {
            "name": "Test",
            "recipeIngredient": ["2 cloves garlic, minced", "1 onion, sliced"],
            "recipeInstructions": [
                {"@type": "HowToStep", "text": "Cook the garlic and onion until soft."}
            ],
        }
    )

    assert recipe.directions == [
        _schema_org.Direction(
            id="step_0",
            text="Cook the garlic and onion until soft.",
            section=None,
            highlights=[
                _schema_org.IngredientHighlight(
                    type="ingredient",
                    text="garlic",
                    ids=["ingredient_0"],
                    start=9,
                    end=15,
                ),
                _schema_org.IngredientHighlight(
                    type="ingredient",
                    text="onion",
                    ids=["ingredient_1"],
                    start=20,
                    end=25,
                ),
            ],
        )
    ]


def test_directions_join_grouped_ingredient_list_with_shared_suffix():
    recipe = _schema_org.Recipe(
        {
            "name": "Test",
            "recipeIngredient": [
                "1 tsp fennel seeds",
                "1 tsp cumin seeds",
                "1 tsp coriander seeds",
            ],
            "recipeInstructions": [
                "Toast the fennel, cumin and coriander seeds in a dry frying pan."
            ],
        }
    )

    assert recipe.directions[0].highlights == [
        _schema_org.IngredientHighlight(
            type="ingredient",
            text="fennel, cumin and coriander seeds",
            ids=["ingredient_0", "ingredient_1", "ingredient_2"],
            start=10,
            end=43,
        )
    ]


def test_directions_reuse_grouped_suffix_reference_within_same_step():
    recipe = _schema_org.Recipe(
        {
            "name": "Test",
            "recipeIngredient": [
                "1 tsp fennel seeds",
                "1 tsp cumin seeds",
                "1 tsp coriander seeds",
            ],
            "recipeInstructions": [
                "Toast the fennel, cumin and coriander seeds. Pour seeds into a grinder."
            ],
        }
    )

    assert recipe.directions[0].highlights == [
        _schema_org.IngredientHighlight(
            type="ingredient",
            text="fennel, cumin and coriander seeds",
            ids=["ingredient_0", "ingredient_1", "ingredient_2"],
            start=10,
            end=43,
        ),
        _schema_org.IngredientHighlight(
            type="ingredient",
            text="seeds",
            ids=["ingredient_0", "ingredient_1", "ingredient_2"],
            start=50,
            end=55,
        ),
    ]


def test_directions_do_not_reuse_grouped_suffix_before_group_is_introduced():
    recipe = _schema_org.Recipe(
        {
            "name": "Test",
            "recipeIngredient": [
                "1 tsp fennel seeds",
                "1 tsp cumin seeds",
                "1 tsp coriander seeds",
            ],
            "recipeInstructions": [
                "Pour seeds into a grinder. Toast the fennel, cumin and coriander seeds."
            ],
        }
    )

    assert recipe.directions[0].highlights == [
        _schema_org.IngredientHighlight(
            type="ingredient",
            text="fennel, cumin and coriander seeds",
            ids=["ingredient_0", "ingredient_1", "ingredient_2"],
            start=37,
            end=70,
        )
    ]


def test_directions_reuse_grouped_suffix_from_prior_groups_only():
    recipe = _schema_org.Recipe(
        {
            "name": "Test",
            "recipeIngredient": [
                "1 tsp fennel seeds",
                "1 tsp cumin seeds",
                "1 tbsp pumpkin seeds",
                "1 tbsp sunflower seeds",
            ],
            "recipeInstructions": [
                "Toast fennel and cumin seeds. Add seeds to the bowl. Toast pumpkin and sunflower seeds."
            ],
        }
    )

    assert recipe.directions[0].highlights == [
        _schema_org.IngredientHighlight(
            type="ingredient",
            text="fennel and cumin seeds",
            ids=["ingredient_0", "ingredient_1"],
            start=6,
            end=28,
        ),
        _schema_org.IngredientHighlight(
            type="ingredient",
            text="seeds",
            ids=["ingredient_0", "ingredient_1"],
            start=34,
            end=39,
        ),
        _schema_org.IngredientHighlight(
            type="ingredient",
            text="pumpkin and sunflower seeds",
            ids=["ingredient_2", "ingredient_3"],
            start=59,
            end=86,
        ),
    ]


def test_directions_reuse_grouped_suffix_from_all_prior_groups():
    recipe = _schema_org.Recipe(
        {
            "name": "Test",
            "recipeIngredient": [
                "1 tsp fennel seeds",
                "1 tsp cumin seeds",
                "1 tbsp pumpkin seeds",
                "1 tbsp sunflower seeds",
            ],
            "recipeInstructions": [
                "Toast fennel and cumin seeds. Toast pumpkin and sunflower seeds. Add seeds to the bowl."
            ],
        }
    )

    assert recipe.directions[0].highlights == [
        _schema_org.IngredientHighlight(
            type="ingredient",
            text="fennel and cumin seeds",
            ids=["ingredient_0", "ingredient_1"],
            start=6,
            end=28,
        ),
        _schema_org.IngredientHighlight(
            type="ingredient",
            text="pumpkin and sunflower seeds",
            ids=["ingredient_2", "ingredient_3"],
            start=36,
            end=63,
        ),
        _schema_org.IngredientHighlight(
            type="ingredient",
            text="seeds",
            ids=["ingredient_0", "ingredient_1", "ingredient_2", "ingredient_3"],
            start=69,
            end=74,
        ),
    ]


def test_directions_include_parsed_amount_with_ingredient_highlight():
    recipe = _schema_org.Recipe(
        {
            "name": "Test",
            "recipeIngredient": ["2 tbsp olive oil"],
            "recipeInstructions": ["Add 2 tbsp olive oil to the pan."],
        }
    )

    assert recipe.directions[0].highlights == [
        _schema_org.IngredientHighlight(
            type="ingredient",
            text="2 tbsp olive oil",
            ids=["ingredient_0"],
            start=4,
            end=20,
        )
    ]


def test_directions_do_not_highlight_unmatched_quantities():
    recipe = _schema_org.Recipe(
        {
            "name": "Test",
            "recipeIngredient": ["1 tsp fennel seeds"],
            "recipeInstructions": ["Toast the fennel seeds for about 3 minutes."],
        }
    )

    assert recipe.directions[0].highlights == [
        _schema_org.IngredientHighlight(
            type="ingredient",
            text="fennel seeds",
            ids=["ingredient_0"],
            start=10,
            end=22,
        )
    ]


def test_directions_prefer_longest_ingredient_match():
    recipe = _schema_org.Recipe(
        {
            "name": "Test",
            "recipeIngredient": ["1 lb beef", "1 lb ground beef"],
            "recipeInstructions": ["Brown the ground beef in a skillet."],
        }
    )

    assert recipe.directions == [
        _schema_org.Direction(
            id="step_0",
            text="Brown the ground beef in a skillet.",
            section=None,
            highlights=[
                _schema_org.IngredientHighlight(
                    type="ingredient",
                    text="ground beef",
                    ids=["ingredient_1"],
                    start=10,
                    end=21,
                )
            ],
        )
    ]


def test_directions_preserve_sections():
    recipe = _schema_org.Recipe(
        {
            "name": "Test",
            "recipeIngredient": ["1 cup rice"],
            "recipeInstructions": [
                {
                    "@type": "HowToSection",
                    "name": "Rice",
                    "itemListElement": [
                        {"@type": "HowToStep", "text": "Rinse the rice well."}
                    ],
                }
            ],
        }
    )

    assert recipe.directions == [
        _schema_org.Direction(
            id="step_0",
            text="Rinse the rice well.",
            section="Rice",
            highlights=[
                _schema_org.IngredientHighlight(
                    type="ingredient",
                    text="rice",
                    ids=["ingredient_0"],
                    start=10,
                    end=14,
                )
            ],
        )
    ]


def test_directions_match_safe_suffix_aliases():
    recipe = _schema_org.Recipe(
        {
            "name": "Test",
            "recipeIngredient": [
                "2 tbsp extra-virgin olive oil",
                "1 cup jasmine rice",
            ],
            "recipeInstructions": [
                "Heat the olive oil, then rinse the rice and cook it."
            ],
        }
    )

    assert recipe.directions == [
        _schema_org.Direction(
            id="step_0",
            text="Heat the olive oil, then rinse the rice and cook it.",
            section=None,
            highlights=[
                _schema_org.IngredientHighlight(
                    type="ingredient",
                    text="olive oil",
                    ids=["ingredient_0"],
                    start=9,
                    end=18,
                ),
                _schema_org.IngredientHighlight(
                    type="ingredient",
                    text="rice",
                    ids=["ingredient_1"],
                    start=35,
                    end=39,
                )
            ],
        )
    ]


def test_directions_do_not_match_overly_generic_single_word_aliases():
    recipe = _schema_org.Recipe(
        {
            "name": "Test",
            "recipeIngredient": ["2 tbsp olive oil"],
            "recipeInstructions": ["Heat the oil in a pan."],
        }
    )

    assert recipe.directions == [
        _schema_org.Direction(
            id="step_0",
            text="Heat the oil in a pan.",
            section=None,
            highlights=[],
        )
    ]


def test_directions_do_not_match_single_word_alias_inside_derived_phrase():
    recipe = _schema_org.Recipe(
        {
            "name": "Test",
            "recipeIngredient": ["4 garlic cloves, thinly sliced"],
            "recipeInstructions": ["Top with garlic chips before serving."],
        }
    )

    assert recipe.directions == [
        _schema_org.Direction(
            id="step_0",
            text="Top with garlic chips before serving.",
            section=None,
            highlights=[],
        )
    ]


def test_directions_do_not_match_single_word_alias_inside_reserved_phrase():
    recipe = _schema_org.Recipe(
        {
            "name": "Test",
            "recipeIngredient": ["1 tsp Aleppo-style pepper", "2 tbsp mixed herbs"],
            "recipeInstructions": [
                "Top with herbs and drizzle over reserved pepper oil."
            ],
        }
    )

    assert recipe.directions == [
        _schema_org.Direction(
            id="step_0",
            text="Top with herbs and drizzle over reserved pepper oil.",
            section=None,
            highlights=[
                _schema_org.IngredientHighlight(
                    type="ingredient",
                    text="herbs",
                    ids=["ingredient_1"],
                    start=9,
                    end=14,
                )
            ],
        )
    ]


def test_directions_do_not_match_transformed_single_word_aliases():
    recipe = _schema_org.Recipe(
        {
            "name": "Test",
            "recipeIngredient": ["2 cups heavy cream", "1 block firm tofu"],
            "recipeInstructions": ["Top with whipped cream and serve with fried tofu."],
        }
    )

    assert recipe.directions == [
        _schema_org.Direction(
            id="step_0",
            text="Top with whipped cream and serve with fried tofu.",
            section=None,
            highlights=[],
        )
    ]


def test_directions_still_match_standalone_single_word_aliases():
    recipe = _schema_org.Recipe(
        {
            "name": "Test",
            "recipeIngredient": ["1 cup jasmine rice", "1 onion, diced"],
            "recipeInstructions": ["Rinse the rice well, then add the onion."],
        }
    )

    assert recipe.directions == [
        _schema_org.Direction(
            id="step_0",
            text="Rinse the rice well, then add the onion.",
            section=None,
            highlights=[
                _schema_org.IngredientHighlight(
                    type="ingredient",
                    text="rice",
                    ids=["ingredient_0"],
                    start=10,
                    end=14,
                ),
                _schema_org.IngredientHighlight(
                    type="ingredient",
                    text="onion",
                    ids=["ingredient_1"],
                    start=34,
                    end=39,
                )
            ],
        )
    ]


def test_directions_match_single_word_alias_after_verb_context():
    recipe = _schema_org.Recipe(
        {
            "name": "Test",
            "recipeIngredient": ["1 packet fast-action yeast", "200g penne pasta"],
            "recipeInstructions": [
                "Mix the milk and yeast together, then boil pasta till done."
            ],
        }
    )

    assert recipe.directions == [
        _schema_org.Direction(
            id="step_0",
            text="Mix the milk and yeast together, then boil pasta till done.",
            section=None,
            highlights=[
                _schema_org.IngredientHighlight(
                    type="ingredient",
                    text="yeast",
                    ids=["ingredient_0"],
                    start=17,
                    end=22,
                ),
                _schema_org.IngredientHighlight(
                    type="ingredient",
                    text="pasta",
                    ids=["ingredient_1"],
                    start=43,
                    end=48,
                )
            ],
        )
    ]


def test_directions_match_single_word_alias_with_preparation_extension():
    recipe = _schema_org.Recipe(
        {
            "name": "Test",
            "recipeIngredient": ["1 hot house cucumber", "1 cup all-purpose flour"],
            "recipeInstructions": [
                "Begin placing cucumber rounds in a bowl and dust with flour as needed."
            ],
        }
    )

    assert recipe.directions == [
        _schema_org.Direction(
            id="step_0",
            text="Begin placing cucumber rounds in a bowl and dust with flour as needed.",
            section=None,
            highlights=[
                _schema_org.IngredientHighlight(
                    type="ingredient",
                    text="cucumber",
                    ids=["ingredient_0"],
                    start=14,
                    end=22,
                ),
                _schema_org.IngredientHighlight(
                    type="ingredient",
                    text="flour",
                    ids=["ingredient_1"],
                    start=54,
                    end=59,
                )
            ],
        )
    ]


def test_directions_match_single_word_alias_with_any_determiner():
    recipe = _schema_org.Recipe(
        {
            "name": "Test",
            "recipeIngredient": ["50g flaked almonds"],
            "recipeInstructions": ["Trim any almonds sticking out of the edges."],
        }
    )

    assert recipe.directions == [
        _schema_org.Direction(
            id="step_0",
            text="Trim any almonds sticking out of the edges.",
            section=None,
            highlights=[
                _schema_org.IngredientHighlight(
                    type="ingredient",
                    text="almonds",
                    ids=["ingredient_0"],
                    start=9,
                    end=16,
                )
            ],
        )
    ]


def test_directions_do_not_match_reserved_single_word_aliases():
    recipe = _schema_org.Recipe(
        {
            "name": "Test",
            "recipeIngredient": ["2 tbsp duck fat"],
            "recipeInstructions": ["Stir through enough of the reserved fat to bind."],
        }
    )

    assert recipe.directions == [
        _schema_org.Direction(
            id="step_0",
            text="Stir through enough of the reserved fat to bind.",
            section=None,
            highlights=[],
        )
    ]


def test_missing_units_serialize_as_null():
    ingredient = _schema_org.Recipe(
        {"name": "Test", "recipeIngredient": ["1 onion, sliced"]}
    ).ingredients[0]

    assert ingredient.amounts == [
        _schema_org.IngredientAmount(
            quantity="1",
            quantity_max="1",
            unit=None,
            text="1",
        )
    ]


def test_time_is_structured_object():
    recipe = _schema_org.Recipe(
        {
            "name": "Test",
            "recipeIngredient": [],
            "prepTime": "PT10M",
            "cookTime": "PT20M",
        }
    )

    assert recipe.time == _schema_org.RecipeTime(
        valueMs=1800000,
        valueFormatted="30 min",
    )


def test_openapi_uses_polymorphic_direction_highlights():
    openapi = create_app().openapi()
    direction_schema = openapi["components"]["schemas"]["Direction"]
    highlight_schema = direction_schema["properties"]["highlights"]["items"]
    ingredient_highlight_schema = openapi["components"]["schemas"]["IngredientHighlight"]
    ingredient_amount_schema = openapi["components"]["schemas"]["IngredientAmount"]
    recipe_schema = openapi["components"]["schemas"]["Recipe"]

    assert highlight_schema["discriminator"]["propertyName"] == "type"
    assert set(highlight_schema["oneOf"][0].keys()) == {"$ref"}
    assert ingredient_highlight_schema["properties"]["ids"]["items"] == {
        "type": "string"
    }
    assert ingredient_amount_schema["properties"]["unit"]["anyOf"] == [
        {"type": "string"},
        {"type": "null"},
    ]
    assert (
        recipe_schema["properties"]["time"]["anyOf"][0]["$ref"]
        == "#/components/schemas/RecipeTime"
    )


def test_ensure_ingredient_parser_ready_warms_once():
    with patch.object(
        _schema_org,
        "_parse_ingredient_sentence",
        return_value=object(),
    ) as parse_ingredient:
        original_ready = _schema_org._ingredient_parser_ready
        _schema_org._ingredient_parser_ready = False
        try:
            _schema_org.ensure_ingredient_parser_ready()
            _schema_org.ensure_ingredient_parser_ready()
        finally:
            _schema_org._ingredient_parser_ready = original_ready

    assert parse_ingredient.call_count == 1
    parse_ingredient.assert_called_once_with("1 cup water")


def test_app_startup_warms_ingredient_parser():
    with patch("chorba.cmd.server.ensure_ingredient_parser_ready") as ready:
        with TestClient(create_app()):
            pass

    ready.assert_called_once_with()
