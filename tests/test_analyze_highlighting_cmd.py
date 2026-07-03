from chorba.cmd import analyze_highlighting


def test_classify_segment_match_recognizes_match_tiers():
    ingredient = {"id": "ingredient_0", "names": ["extra virgin olive oil"]}

    assert (
        analyze_highlighting.classify_segment_match(
            "extra virgin olive oil", ingredient
        )
        == "exact_name"
    )
    assert (
        analyze_highlighting.classify_segment_match("olive oil", ingredient)
        == "multi_word_alias"
    )


def test_detect_segment_issues_flags_single_word_alias_in_derived_phrase():
    ingredient_lookup = {
        "ingredient_0": {"id": "ingredient_0", "names": ["Aleppo-style pepper"]}
    }
    step = {
        "id": "step_0",
        "text": "Drizzle over reserved pepper oil.",
        "segments": [
            {
                "type": "ingredient",
                "text": "pepper",
                "id": "ingredient_0",
                "start": 23,
                "end": 29,
            }
        ],
    }

    issues, counters = analyze_highlighting.detect_segment_issues(
        "example.com", "https://example.com/recipe", step, ingredient_lookup
    )

    assert counters["match_type:single_word_alias"] == 1
    assert [issue.category for issue in issues] == ["suspicious_single_word_alias"]


def test_detect_missing_highlights_flags_explicit_multi_word_mentions():
    ingredients = [{"id": "ingredient_0", "names": ["extra virgin olive oil"]}]
    step = {
        "id": "step_0",
        "text": "Heat the olive oil in a skillet.",
        "segments": [
            {
                "type": "instruction",
                "text": "Heat the olive oil in a skillet.",
                "start": 0,
                "end": 32,
            }
        ],
    }

    issues = analyze_highlighting.detect_missing_highlights(
        "example.com", "https://example.com/recipe", step, ingredients
    )

    assert [issue.category for issue in issues] == ["missing_multi_word_match"]


def test_detect_parser_name_issues_flags_suspicious_names():
    ingredient = {
        "id": "ingredient_0",
        "sentence": "juice &frac12; lemon",
        "names": ["juice", "lemon"],
    }

    issues = analyze_highlighting.detect_parser_name_issues(
        "example.com", "https://example.com/recipe", ingredient
    )

    assert [issue.category for issue in issues] == ["parser_suspicious_name"]


def test_suspicious_matcher_names_do_not_generate_aliases():
    assert analyze_highlighting.ingredient_candidates(
        {"id": "ingredient_0", "names": ["juice", "lemon"]}
    ) == ({"juice", "lemon"}, set(), set())


def test_missing_highlights_skips_intentional_transformed_single_word_references():
    ingredients = [{"id": "ingredient_0", "names": ["heavy cream"]}]
    step = {
        "id": "step_0",
        "text": "Top with whipped cream and serve.",
        "segments": [
            {
                "type": "instruction",
                "text": "Top with whipped cream and serve.",
                "start": 0,
                "end": 33,
            }
        ],
    }

    assert (
        analyze_highlighting.detect_missing_highlights(
            "example.com", "https://example.com/recipe", step, ingredients
        )
        == []
    )


def test_suspicious_single_word_alias_ignores_punctuation_separated_words():
    ingredient_lookup = {
        "ingredient_0": {
            "id": "ingredient_0",
            "names": ["no-salt-added diced tomatoes"],
        }
    }
    step = {
        "id": "step_0",
        "text": "Add tomatoes, broth and seasoning mix; stir.",
        "segments": [
            {
                "type": "ingredient",
                "text": "tomatoes",
                "id": "ingredient_0",
                "start": 4,
                "end": 12,
            }
        ],
    }

    issues, _ = analyze_highlighting.detect_segment_issues(
        "example.com", "https://example.com/recipe", step, ingredient_lookup
    )

    assert issues == []


def test_missing_highlights_skips_transformed_next_word_phrases():
    ingredients = [{"id": "ingredient_0", "names": ["honey mustard"]}]
    step = {
        "id": "step_0",
        "text": "Cover with the rest of the mustard sauce mixture.",
        "segments": [
            {
                "type": "instruction",
                "text": "Cover with the rest of the mustard sauce mixture.",
                "start": 0,
                "end": 49,
            }
        ],
    }

    assert (
        analyze_highlighting.detect_missing_highlights(
            "example.com", "https://example.com/recipe", step, ingredients
        )
        == []
    )
