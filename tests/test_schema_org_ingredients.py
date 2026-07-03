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


def test_directions_include_linked_segments():
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
            segments=[
                _schema_org.InstructionSegment(
                    type="instruction", text="Cook the ", start=0, end=9
                ),
                _schema_org.IngredientSegment(
                    type="ingredient",
                    text="garlic",
                    id="ingredient_0",
                    start=9,
                    end=15,
                ),
                _schema_org.InstructionSegment(
                    type="instruction", text=" and ", start=15, end=20
                ),
                _schema_org.IngredientSegment(
                    type="ingredient",
                    text="onion",
                    id="ingredient_1",
                    start=20,
                    end=25,
                ),
                _schema_org.InstructionSegment(
                    type="instruction", text=" until soft.", start=25, end=37
                ),
            ],
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
            segments=[
                _schema_org.InstructionSegment(
                    type="instruction", text="Brown the ", start=0, end=10
                ),
                _schema_org.IngredientSegment(
                    type="ingredient",
                    text="ground beef",
                    id="ingredient_1",
                    start=10,
                    end=21,
                ),
                _schema_org.InstructionSegment(
                    type="instruction", text=" in a skillet.", start=21, end=35
                ),
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
            segments=[
                _schema_org.InstructionSegment(
                    type="instruction", text="Rinse the ", start=0, end=10
                ),
                _schema_org.IngredientSegment(
                    type="ingredient",
                    text="rice",
                    id="ingredient_0",
                    start=10,
                    end=14,
                ),
                _schema_org.InstructionSegment(
                    type="instruction", text=" well.", start=14, end=20
                ),
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
            segments=[
                _schema_org.InstructionSegment(
                    type="instruction", text="Heat the ", start=0, end=9
                ),
                _schema_org.IngredientSegment(
                    type="ingredient",
                    text="olive oil",
                    id="ingredient_0",
                    start=9,
                    end=18,
                ),
                _schema_org.InstructionSegment(
                    type="instruction",
                    text=", then rinse the ",
                    start=18,
                    end=35,
                ),
                _schema_org.IngredientSegment(
                    type="ingredient",
                    text="rice",
                    id="ingredient_1",
                    start=35,
                    end=39,
                ),
                _schema_org.InstructionSegment(
                    type="instruction", text=" and cook it.", start=39, end=52
                ),
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
            segments=[
                _schema_org.InstructionSegment(
                    type="instruction",
                    text="Heat the oil in a pan.",
                    start=0,
                    end=22,
                )
            ],
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
            segments=[
                _schema_org.InstructionSegment(
                    type="instruction",
                    text="Top with garlic chips before serving.",
                    start=0,
                    end=37,
                )
            ],
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
            segments=[
                _schema_org.InstructionSegment(
                    type="instruction",
                    text="Top with ",
                    start=0,
                    end=9,
                ),
                _schema_org.IngredientSegment(
                    type="ingredient",
                    text="herbs",
                    id="ingredient_1",
                    start=9,
                    end=14,
                ),
                _schema_org.InstructionSegment(
                    type="instruction",
                    text=" and drizzle over reserved pepper oil.",
                    start=14,
                    end=52,
                ),
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
            segments=[
                _schema_org.InstructionSegment(
                    type="instruction",
                    text="Top with whipped cream and serve with fried tofu.",
                    start=0,
                    end=49,
                )
            ],
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
            segments=[
                _schema_org.InstructionSegment(
                    type="instruction", text="Rinse the ", start=0, end=10
                ),
                _schema_org.IngredientSegment(
                    type="ingredient",
                    text="rice",
                    id="ingredient_0",
                    start=10,
                    end=14,
                ),
                _schema_org.InstructionSegment(
                    type="instruction", text=" well, then add the ", start=14, end=34
                ),
                _schema_org.IngredientSegment(
                    type="ingredient",
                    text="onion",
                    id="ingredient_1",
                    start=34,
                    end=39,
                ),
                _schema_org.InstructionSegment(
                    type="instruction", text=".", start=39, end=40
                ),
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
            segments=[
                _schema_org.InstructionSegment(
                    type="instruction", text="Mix the milk and ", start=0, end=17
                ),
                _schema_org.IngredientSegment(
                    type="ingredient",
                    text="yeast",
                    id="ingredient_0",
                    start=17,
                    end=22,
                ),
                _schema_org.InstructionSegment(
                    type="instruction", text=" together, then boil ", start=22, end=43
                ),
                _schema_org.IngredientSegment(
                    type="ingredient",
                    text="pasta",
                    id="ingredient_1",
                    start=43,
                    end=48,
                ),
                _schema_org.InstructionSegment(
                    type="instruction", text=" till done.", start=48, end=59
                ),
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
            segments=[
                _schema_org.InstructionSegment(
                    type="instruction", text="Begin placing ", start=0, end=14
                ),
                _schema_org.IngredientSegment(
                    type="ingredient",
                    text="cucumber",
                    id="ingredient_0",
                    start=14,
                    end=22,
                ),
                _schema_org.InstructionSegment(
                    type="instruction",
                    text=" rounds in a bowl and dust with ",
                    start=22,
                    end=54,
                ),
                _schema_org.IngredientSegment(
                    type="ingredient",
                    text="flour",
                    id="ingredient_1",
                    start=54,
                    end=59,
                ),
                _schema_org.InstructionSegment(
                    type="instruction", text=" as needed.", start=59, end=70
                ),
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
            segments=[
                _schema_org.InstructionSegment(
                    type="instruction", text="Trim any ", start=0, end=9
                ),
                _schema_org.IngredientSegment(
                    type="ingredient",
                    text="almonds",
                    id="ingredient_0",
                    start=9,
                    end=16,
                ),
                _schema_org.InstructionSegment(
                    type="instruction",
                    text=" sticking out of the edges.",
                    start=16,
                    end=43,
                ),
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
            segments=[
                _schema_org.InstructionSegment(
                    type="instruction",
                    text="Stir through enough of the reserved fat to bind.",
                    start=0,
                    end=48,
                )
            ],
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


def test_openapi_uses_polymorphic_direction_segments():
    openapi = create_app().openapi()
    direction_schema = openapi["components"]["schemas"]["Direction"]
    segment_schema = direction_schema["properties"]["segments"]["items"]
    ingredient_amount_schema = openapi["components"]["schemas"]["IngredientAmount"]
    recipe_schema = openapi["components"]["schemas"]["Recipe"]

    assert segment_schema["discriminator"]["propertyName"] == "type"
    assert set(segment_schema["oneOf"][0].keys()) == {"$ref"}
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
