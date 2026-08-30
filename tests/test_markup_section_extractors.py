import json
from importlib import import_module

import pytest

from chorba.lib.markup import _schema_org


def _html(recipe_ingredients, rendered=""):
    payload = {
        "props": {
            "pageProps": {"recipe": {"recipeIngredients": recipe_ingredients}}
        }
    }
    return (
        f"<html><body>{rendered}"
        f'<script id="__NEXT_DATA__" type="application/json">'
        f"{json.dumps(payload)}</script></body></html>"
    )


def _ingredient(quantity, title, *, shorthand=None, unit_title=None):
    units = []
    if shorthand is not None or unit_title is not None:
        units.append({"shorthand": shorthand, "title": unit_title})
    return {
        "typeHandle": "ingredient",
        "quantity": quantity,
        "unit": units,
        "ingredient": [{"title": title}],
    }


def _extract(schema_ingredients, html):
    module = import_module("chorba.lib.markup._section_extractors")
    recipe = _schema_org.Recipe({"recipeIngredient": schema_ingredients})
    return module.MobIngredientSectionExtractor().extract(recipe, html)


def test_extracts_grouped_sections_and_preserves_header_punctuation():
    records = [
        {"typeHandle": "header", "heading": "For the sauce:"},
        _ingredient("2", "Olive Oil", shorthand="tbsp", unit_title="Tablespoon"),
        {"typeHandle": "header", "heading": "To finish!"},
        _ingredient("1", "Garlic", shorthand="", unit_title="Clove"),
    ]

    assert _extract(
        ["2tbsp Olive Oil", "1Clove Garlic"], _html(records)
    ) == ["For the sauce:", "To finish!"]


@pytest.mark.parametrize("heading", ["", "  \t\n"])
def test_returns_none_for_empty_or_whitespace_only_header(heading):
    records = [
        {"typeHandle": "header", "heading": heading},
        _ingredient("1", "Onion"),
    ]

    assert _extract(["1 Onion"], _html(records)) is None


def test_extracts_initial_ungrouped_ingredients():
    records = [
        _ingredient("1", "Onion"),
        {"typeHandle": "header", "heading": "For the sauce"},
        _ingredient("200", "Tomato", shorthand="g", unit_title="Gram"),
    ]

    assert _extract(["1 Onion", "200g Tomato"], _html(records)) == [
        None,
        "For the sauce",
    ]


def test_assigns_duplicate_ingredients_to_their_respective_groups():
    records = [
        {"typeHandle": "header", "heading": "Base"},
        _ingredient("1", "Lemon"),
        {"typeHandle": "header", "heading": "Dressing"},
        _ingredient("1", "Lemon"),
    ]

    assert _extract(["1 Lemon", "1 Lemon"], _html(records)) == [
        "Base",
        "Dressing",
    ]


def test_extracts_final_ingredient_when_it_is_absent_from_rendered_dom():
    records = [
        {"typeHandle": "header", "heading": "Main"},
        _ingredient("1", "Carrot"),
        _ingredient(None, "Salt"),
    ]

    html = _html(records, rendered="<ul><li>1 Carrot</li></ul>")

    assert _extract(["1 Carrot", "Salt"], html) == ["Main", "Main"]


def test_returns_none_when_next_data_script_is_missing():
    assert _extract(["1 Onion"], "<html><body>1 Onion</body></html>") is None


def test_returns_none_when_next_data_is_invalid_json():
    html = '<script id="__NEXT_DATA__">{not valid json</script>'

    assert _extract(["1 Onion"], html) is None


@pytest.mark.parametrize(
    "payload",
    [
        None,
        {},
        {"props": None},
        {"props": {"pageProps": {"recipe": {"recipeIngredients": {}}}}},
        {
            "props": {
                "pageProps": {
                    "recipe": {
                        "recipeIngredients": [
                            {
                                "typeHandle": "ingredient",
                                "quantity": "1",
                                "unit": [],
                                "ingredient": [],
                            }
                        ]
                    }
                }
            }
        },
    ],
)
def test_returns_none_for_malformed_nested_data(payload):
    html = f'<script id="__NEXT_DATA__">{json.dumps(payload)}</script>'

    assert _extract(["1 Onion"], html) is None


@pytest.mark.parametrize(
    "record",
    [
        {"typeHandle": "header", "heading": False},
        _ingredient(False, "Onion"),
        {
            "typeHandle": "ingredient",
            "quantity": "1",
            "unit": [False],
            "ingredient": [{"title": "Onion"}],
        },
        _ingredient("1", False),
        [],
        {"typeHandle": "note"},
    ],
    ids=[
        "header",
        "quantity",
        "unit-entry",
        "ingredient-title",
        "non-dictionary-record",
        "unknown-type-handle",
    ],
)
def test_returns_none_for_malformed_recipe_ingredient_record(record):
    assert _extract(["1 Onion"], _html([record])) is None


@pytest.mark.parametrize(
    "shorthand",
    [False, 0, [], {}],
    ids=["false", "zero", "list", "dictionary"],
)
def test_returns_none_for_present_non_string_unit_shorthand(shorthand):
    records = [
        _ingredient(
            "1",
            "Onion",
            shorthand=shorthand,
            unit_title="Tablespoon",
        )
    ]

    assert _extract(["1Tablespoon Onion"], _html(records)) is None


def test_returns_none_when_reconstructed_ingredient_mismatches_schema():
    records = [_ingredient("1", "Onion")]

    assert _extract(["2 Onions"], _html(records)) is None


def test_returns_none_when_reconstructed_ingredient_count_mismatches_schema():
    records = [_ingredient("1", "Onion"), _ingredient("2", "Carrots")]

    assert _extract(["1 Onion"], _html(records)) is None


def test_default_registry_contains_only_the_exact_mob_hostname():
    module = import_module("chorba.lib.markup._section_extractors")

    assert set(module.DEFAULT_INGREDIENT_SECTION_EXTRACTORS) == {"www.mob.co.uk"}
    assert isinstance(
        module.DEFAULT_INGREDIENT_SECTION_EXTRACTORS["www.mob.co.uk"],
        module.MobIngredientSectionExtractor,
    )
