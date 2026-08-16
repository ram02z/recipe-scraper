from chorba.lib.markup import _hydrators
from chorba.lib.markup import _schema_org
from parsel import Selector


def test_normalizes_spacing_entities_and_checkbox_markers():
    assert _hydrators._normalize_match_text("\u25a2  1&nbsp; cup\u00a0rice") == "1 cup rice"


def test_texts_match_parenthesized_and_comma_notes():
    assert _hydrators._texts_match(
        "1 onion (diced, optional)",
        ["1 onion, diced, optional"],
    )


def test_texts_match_dash_and_quote_variants():
    assert _hydrators._texts_match(
        '6 - 10 dried chillies (cut into 2cm/ 3/4" pieces)',
        ["6 - 10 dried chillies, cut into 2cm/ 3/4” pieces"],
    )


def test_collects_li_candidates_with_text_variants():
    selector = Selector(
        text="""
        <div>
          <li aria-label="1 cup rice">
            <span class="screen-reader-text">▢</span>
            <span class="wprm-recipe-ingredient-amount">1</span>
            <span class="wprm-recipe-ingredient-unit">cup</span>
            <span class="wprm-recipe-ingredient-name">rice</span>
          </li>
        </div>
        """
    )

    candidates = _hydrators._ingredient_candidates(selector)

    assert len(candidates) == 1
    assert candidates[0].order == 0
    assert "1 cup rice" in [
        _hydrators._normalize_match_text(text)
        for text in candidates[0].text_variants
    ]


def test_aligns_schema_ingredients_to_candidates_in_order():
    selector = Selector(
        text="""
        <div>
          <li>ad marker</li>
          <li>1 cup rice</li>
          <li>2 tbsp soy sauce</li>
        </div>
        """
    )
    candidates = _hydrators._ingredient_candidates(selector)

    aligned = _hydrators._align_ingredients(
        ["1 cup rice", "2 tbsp soy sauce"], candidates
    )

    assert aligned is not None
    assert [candidate.order for candidate in aligned] == [1, 2]


def test_alignment_rejects_missing_match():
    selector = Selector(text="<div><li>1 cup rice</li></div>")
    candidates = _hydrators._ingredient_candidates(selector)

    assert _hydrators._align_ingredients(
        ["1 cup rice", "2 tbsp soy sauce"], candidates
    ) is None


def test_hydrates_sections_from_explicit_group_containers():
    html = """
    <div class="wprm-recipe-ingredients-container">
      <div class="wprm-recipe-ingredient-group">
        <h4 class="wprm-recipe-group-name wprm-recipe-ingredient-group-name">Sauce</h4>
        <ul>
          <li class="wprm-recipe-ingredient">
            <span class="wprm-recipe-ingredient-amount">2</span>
            <span class="wprm-recipe-ingredient-unit">tbsp</span>
            <span class="wprm-recipe-ingredient-name">soy sauce</span>
          </li>
        </ul>
      </div>
      <div class="wprm-recipe-ingredient-group">
        <h4 class="wprm-recipe-group-name wprm-recipe-ingredient-group-name">Stir Fry</h4>
        <ul><li class="wprm-recipe-ingredient">1 cup broccoli</li></ul>
      </div>
    </div>
    """

    recipe = _schema_org.Recipe(
        {"recipeIngredient": ["2 tbsp soy sauce", "1 cup broccoli"]}
    )

    hydrated = _hydrators.IngredientSectionHydrator().hydrate(
        recipe,
        html,
    )

    assert hydrated is not recipe
    assert [ingredient.section for ingredient in hydrated.ingredients] == [
        "Sauce",
        "Stir Fry",
    ]


def test_hydrates_unheaded_first_group_as_none():
    html = """
    <div class="wprm-recipe-ingredients-container">
      <div class="wprm-recipe-ingredient-group">
        <ul><li class="wprm-recipe-ingredient">4 chicken thighs</li></ul>
      </div>
      <div class="wprm-recipe-ingredient-group">
        <h4 class="wprm-recipe-ingredient-group-name">Marinade</h4>
        <ul><li class="wprm-recipe-ingredient">1 tbsp soy sauce</li></ul>
      </div>
    </div>
    """

    recipe = _schema_org.Recipe(
        {"recipeIngredient": ["4 chicken thighs", "1 tbsp soy sauce"]}
    )

    hydrated = _hydrators.IngredientSectionHydrator().hydrate(
        recipe,
        html,
    )

    assert [ingredient.section for ingredient in hydrated.ingredients] == [None, "Marinade"]


def test_hydrates_sections_from_generic_heading_list_adjacency():
    html = """
    <section data-testid="recipe-ingredients">
      <h2>Ingredients</h2>
      <h3>For the base</h3>
      <div><ul><li>1 cup rice</li></ul></div>
      <h3>For the sauce</h3>
      <div><ul><li>2 tbsp soy sauce</li></ul></div>
    </section>
    """

    recipe = _schema_org.Recipe(
        {"recipeIngredient": ["1 cup rice", "2 tbsp soy sauce"]}
    )

    hydrated = _hydrators.IngredientSectionHydrator().hydrate(
        recipe,
        html,
    )

    assert [ingredient.section for ingredient in hydrated.ingredients] == [
        "For the base",
        "For the sauce",
    ]


def test_hydrator_returns_same_recipe_when_alignment_fails():
    html = """
    <div class="wprm-recipe-ingredients-container">
      <h4>Sauce</h4>
      <ul><li>1 cup rice</li></ul>
    </div>
    """

    recipe = _schema_org.Recipe(
        {"recipeIngredient": ["1 cup rice", "2 tbsp soy sauce"]}
    )

    hydrated = _hydrators.IngredientSectionHydrator().hydrate(
        recipe,
        html,
    )

    assert hydrated is recipe
    assert [ingredient.section for ingredient in hydrated.ingredients] == [None, None]
