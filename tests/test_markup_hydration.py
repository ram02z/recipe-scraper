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


def test_alignment_resolves_repeated_text_from_complete_sequence():
    selector = Selector(
        text="""
        <ul>
          <li>1 tsp sesame oil</li>
          <li>1 tbsp light soy sauce</li>
          <li>1 egg</li>
          <li>4 tbsp vinegar</li>
          <li>1 tbsp light soy sauce</li>
        </ul>
        """
    )
    candidates = _hydrators._ingredient_candidates(selector)

    aligned = _hydrators._align_ingredients(
        [
            "1 tsp sesame oil",
            "1 tbsp light soy sauce",
            "1 egg",
            "4 tbsp vinegar",
            "1 tbsp light soy sauce",
        ],
        candidates,
    )

    assert aligned is not None
    assert [candidate.order for candidate in aligned] == [0, 1, 2, 3, 4]


def test_alignment_rejects_multiple_complete_sequences():
    selector = Selector(text="<ul><li>1 tsp salt</li><li>1 tsp salt</li></ul>")
    candidates = _hydrators._ingredient_candidates(selector)

    assert _hydrators._align_ingredients(["1 tsp salt"], candidates) is None


def test_alignment_handles_long_unique_sequence_without_recursion(monkeypatch):
    values = [str(index) for index in range(1200)]
    candidates = [
        _hydrators._IngredientCandidate(
            selector=Selector(text="<li></li>"),
            order=index,
            text_variants=[value],
        )
        for index, value in enumerate(values)
    ]
    monkeypatch.setattr(
        _hydrators,
        "_texts_match",
        lambda schema_text, candidate_texts: schema_text == candidate_texts[0],
    )

    aligned = _hydrators._align_ingredients(values, candidates)

    assert aligned is not None
    assert [candidate.order for candidate in aligned] == list(range(1200))


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


def test_hydrates_repeated_ingredients_from_unique_bbc_sequence():
    html = """
    <section>
      <h2>Ingredients</h2>
      <h3>For the marinated chicken</h3>
      <div><ul>
        <li>1 tsp sesame oil</li>
        <li>1 tbsp light soy sauce</li>
        <li>1 egg</li>
      </ul></div>
      <h3>For the batter</h3>
      <div><ul><li>5 tbsp cornflour</li></ul></div>
      <h3>For the stir fry</h3>
      <div><ul><li>1 red onion</li></ul></div>
      <h3>For the sauce</h3>
      <div><ul>
        <li>4 tbsp vinegar</li>
        <li>1 tbsp light soy sauce</li>
      </ul></div>
    </section>
    """
    recipe = _schema_org.Recipe(
        {
            "recipeIngredient": [
                "1 tsp sesame oil",
                "1 tbsp light soy sauce",
                "1 egg",
                "5 tbsp cornflour",
                "1 red onion",
                "4 tbsp vinegar",
                "1 tbsp light soy sauce",
            ]
        }
    )

    hydrated = _hydrators.IngredientSectionHydrator().hydrate(recipe, html)

    assert [ingredient.section for ingredient in hydrated.ingredients] == [
        "For the marinated chicken",
        "For the marinated chicken",
        "For the marinated chicken",
        "For the batter",
        "For the stir fry",
        "For the sauce",
        "For the sauce",
    ]


def test_generic_sections_support_h1_and_h2_headings():
    html = """
    <section><h3>Ingredients</h3>
      <h1>Base</h1><ul><li>1 cup rice</li></ul>
      <h2>Sauce</h2><ul><li>2 tbsp soy sauce</li></ul>
    </section>
    """
    recipe = _schema_org.Recipe(
        {"recipeIngredient": ["1 cup rice", "2 tbsp soy sauce"]}
    )

    hydrated = _hydrators.IngredientSectionHydrator().hydrate(recipe, html)

    assert [item.section for item in hydrated.ingredients] == ["Base", "Sauce"]


def test_ingredients_anchor_ignores_itself_and_earlier_headings():
    html = """
    <section><h1>Recipe title</h1><h2>Ingredients</h2>
      <ul><li>1 cup rice</li></ul>
      <h2>Sauce</h2><ul><li>2 tbsp soy sauce</li></ul>
    </section>
    """
    recipe = _schema_org.Recipe(
        {"recipeIngredient": ["1 cup rice", "2 tbsp soy sauce"]}
    )

    hydrated = _hydrators.IngredientSectionHydrator().hydrate(recipe, html)

    assert [item.section for item in hydrated.ingredients] == [None, "Sauce"]


def test_ingredients_anchor_normalizes_nested_text_case_entities_and_punctuation():
    html = """
    <section><h3>Recipe title</h3><h2><span>InGreDients&#58;</span></h2>
      <ul><li>1 cup rice</li></ul>
      <h3>Finish</h3><ul><li>1 tsp salt</li></ul>
    </section>
    """
    recipe = _schema_org.Recipe(
        {"recipeIngredient": ["1 cup rice", "1 tsp salt"]}
    )

    hydrated = _hydrators.IngredientSectionHydrator().hydrate(recipe, html)

    assert [item.section for item in hydrated.ingredients] == [None, "Finish"]


def test_singular_ingredient_anchor_is_not_a_section():
    html = """
    <section><h2>Ingredient:</h2>
      <ul><li>1 cup rice</li></ul>
      <h3>Finish</h3><ul><li>1 tsp salt</li></ul>
    </section>
    """
    recipe = _schema_org.Recipe(
        {"recipeIngredient": ["1 cup rice", "1 tsp salt"]}
    )

    hydrated = _hydrators.IngredientSectionHydrator().hydrate(recipe, html)

    assert [item.section for item in hydrated.ingredients] == [None, "Finish"]


def test_ingredients_for_sauce_remains_a_section_heading():
    html = """
    <section><h2>Ingredients</h2>
      <h3>Ingredients for the sauce</h3>
      <ul><li>2 tbsp soy sauce</li></ul>
      <h3>Finish</h3><ul><li>1 tsp salt</li></ul>
    </section>
    """
    recipe = _schema_org.Recipe(
        {"recipeIngredient": ["2 tbsp soy sauce", "1 tsp salt"]}
    )

    hydrated = _hydrators.IngredientSectionHydrator().hydrate(recipe, html)

    assert [item.section for item in hydrated.ingredients] == [
        "Ingredients for the sauce",
        "Finish",
    ]


def test_document_root_scope_disables_generic_headings():
    html = """
    <h2>Base</h2><ul><li>1 cup rice</li></ul>
    <main><h2>Sauce</h2><ul><li>2 tbsp soy sauce</li></ul></main>
    """
    recipe = _schema_org.Recipe(
        {"recipeIngredient": ["1 cup rice", "2 tbsp soy sauce"]}
    )

    hydrated = _hydrators.IngredientSectionHydrator().hydrate(recipe, html)

    assert [item.section for item in hydrated.ingredients] == [None, None]


def test_document_root_scope_preserves_explicit_group_sections():
    html = """
    <div class="wprm-recipe-ingredient-group">
      <h4 class="wprm-recipe-ingredient-group-name">Base</h4>
      <ul><li>1 cup rice</li></ul>
    </div>
    <div class="wprm-recipe-ingredient-group">
      <h4 class="wprm-recipe-ingredient-group-name">Sauce</h4>
      <ul><li>2 tbsp soy sauce</li></ul>
    </div>
    """
    recipe = _schema_org.Recipe(
        {"recipeIngredient": ["1 cup rice", "2 tbsp soy sauce"]}
    )

    hydrated = _hydrators.IngredientSectionHydrator().hydrate(recipe, html)

    assert [item.section for item in hydrated.ingredients] == ["Base", "Sauce"]


def test_generic_heading_lookup_does_not_expand_above_narrow_scope():
    html = """
    <section><h2>Base</h2>
      <ul><li>1 cup rice</li><li>1 tsp salt</li></ul>
    </section>
    """
    recipe = _schema_org.Recipe(
        {"recipeIngredient": ["1 cup rice", "1 tsp salt"]}
    )

    hydrated = _hydrators.IngredientSectionHydrator().hydrate(recipe, html)

    assert [item.section for item in hydrated.ingredients] == [None, None]


def test_hydrator_returns_same_recipe_for_ambiguous_alignment():
    html = "<section><ul><li>1 tsp salt</li><li>1 tsp salt</li></ul></section>"
    recipe = _schema_org.Recipe({"recipeIngredient": ["1 tsp salt"]})

    hydrated = _hydrators.IngredientSectionHydrator().hydrate(recipe, html)

    assert hydrated is recipe


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
