from datetime import timedelta
from fractions import Fraction
import re
from typing import Annotated, Literal

from pydantic import Field, TypeAdapter, computed_field
from pydantic.dataclasses import dataclass


timedelta_adapter = TypeAdapter(timedelta)
_ingredient_parser_ready = False
_BLOCKED_SINGLE_WORD_ALIASES = {
    "oil",
    "sauce",
    "paste",
    "milk",
    "juice",
    "broth",
    "stock",
    "water",
    "cream",
    "fat",
    "mixture",
    "filling",
    "seasoning",
    "mix",
}
_BLOCKED_ALIAS_EXTENSION_WORDS = {
    "chips",
    "oil",
    "paste",
    "sauce",
    "broth",
    "stock",
    "juice",
    "milk",
    "powder",
    "crumbs",
    "leaves",
    "mix",
}
_PREPARATION_EXTENSION_WORDS = {
    "cubes",
    "florets",
    "leaves",
    "pieces",
    "rounds",
    "slices",
    "wedges",
}
_SUSPICIOUS_MATCHER_NAMES = {
    "combination",
    "juice",
    "lengthways",
}
_TRANSFORMED_INGREDIENT_WORDS = {
    "baked",
    "crispy",
    "fried",
    "pickled",
    "toasted",
    "whipped",
}
_SINGLE_WORD_ALIAS_PREVIOUS_WORDS = {
    "a",
    "an",
    "any",
    "each",
    "more",
    "remaining",
    "some",
    "the",
}
_SINGLE_WORD_ALIAS_NEXT_WORDS = {
    "and",
    "are",
    "as",
    "before",
    "can",
    "for",
    "from",
    "in",
    "into",
    "is",
    "on",
    "or",
    "over",
    "then",
    "to",
    "until",
    "well",
    "were",
    "with",
}
_SINGLE_WORD_ALIAS_VERBS = {
    "add",
    "arrange",
    "blend",
    "boil",
    "brush",
    "bring",
    "cook",
    "drizzle",
    "flip",
    "fold",
    "heat",
    "mix",
    "place",
    "placing",
    "pour",
    "rinse",
    "scatter",
    "season",
    "serve",
    "sprinkle",
    "stir",
    "top",
    "transfer",
    "whisk",
}


def _parse_duration_ms(value: str | None) -> int | None:
    if not value:
        return None

    try:
        duration = timedelta_adapter.validate_python(value)
    except Exception:
        return None

    return int(duration.total_seconds() * 1000)


def _format_duration_ms(duration_ms: int | None) -> str | None:
    if duration_ms is None or duration_ms == 0:
        return None

    total_minutes = duration_ms // 60000
    hours, minutes = divmod(total_minutes, 60)

    if hours == 0:
        return f"{total_minutes} min"
    if minutes == 0:
        return f"{hours} hr"
    return f"{hours} hr {minutes} min"


def _first_url(value) -> str | None:
    if isinstance(value, str):
        return value

    if isinstance(value, dict):
        for key in ["contentUrl", "embedUrl", "url", "thumbnailUrl"]:
            candidate = _first_url(value.get(key))
            if candidate:
                return candidate
        return None

    if isinstance(value, list):
        for item in value:
            candidate = _first_url(item)
            if candidate:
                return candidate

    return None


def _image_url(image) -> str | None:
    return _first_url(image)


def _thumbnail_url(thumbnail) -> str | None:
    return _first_url(thumbnail)


def _video_url(video) -> str | None:
    if isinstance(video, str):
        return video

    if isinstance(video, dict):
        for key in ["contentUrl", "embedUrl", "url"]:
            candidate = _first_url(video.get(key))
            if candidate:
                return candidate

    if isinstance(video, list):
        for item in video:
            candidate = _video_url(item)
            if candidate:
                return candidate

    return None


def _video_thumbnail_url(video) -> str | None:
    if isinstance(video, dict):
        candidate = _first_url(video.get("thumbnailUrl"))
        if candidate:
            return candidate

        thumbnail = video.get("thumbnail")
        if thumbnail is not None:
            return _first_url(thumbnail)

    if isinstance(video, list):
        for item in video:
            candidate = _video_thumbnail_url(item)
            if candidate:
                return candidate

    return None


@dataclass
class IngredientAmount:
    quantity: str
    quantity_max: str
    unit: str | None
    text: str


@dataclass
class Ingredient:
    id: str
    sentence: str
    names: list[str]
    amounts: list[IngredientAmount]
    size: str | None
    preparation: str | None
    comment: str | None
    purpose: str | None


@dataclass
class IngredientHighlight:
    type: Literal["ingredient"]
    text: str
    ids: list[str]
    start: int
    end: int


DirectionHighlight = Annotated[IngredientHighlight, Field(discriminator="type")]


@dataclass
class Direction:
    id: str
    text: str
    section: str | None
    highlights: list[DirectionHighlight]


@dataclass
class RecipeTime:
    valueMs: int
    valueFormatted: str


def _fraction_to_string(value: Fraction | str) -> str:
    if isinstance(value, Fraction):
        if value.denominator == 1:
            return str(value.numerator)
        return f"{value.numerator}/{value.denominator}"
    return value


def _optional_text(value: str | None) -> str | None:
    if value is None:
        return None

    stripped = value.strip()
    return stripped or None


def _normalize_ingredient_amount(amount) -> list[IngredientAmount]:
    nested_amounts = getattr(amount, "amounts", None)
    if nested_amounts is not None:
        normalized_amounts = []
        for nested_amount in nested_amounts:
            normalized_amounts.extend(_normalize_ingredient_amount(nested_amount))
        return normalized_amounts

    return [
        IngredientAmount(
            quantity=_fraction_to_string(amount.quantity),
            quantity_max=_fraction_to_string(amount.quantity_max),
            unit=_optional_text(amount.unit),
            text=amount.text,
        )
    ]


def _parse_ingredient_sentence(sentence: str):
    from ingredient_parser import parse_ingredient

    return parse_ingredient(sentence, string_units=True)


def ensure_ingredient_parser_ready() -> None:
    global _ingredient_parser_ready

    if _ingredient_parser_ready:
        return

    _parse_ingredient_sentence("1 cup water")
    _ingredient_parser_ready = True


def _normalize_ingredient(sentence: str, ingredient_id: str) -> Ingredient:
    try:
        parsed = _parse_ingredient_sentence(sentence)
    except Exception:
        return Ingredient(
            id=ingredient_id,
            sentence=sentence,
            names=[],
            amounts=[],
            size=None,
            preparation=None,
            comment=None,
            purpose=None,
        )

    amounts = []
    for amount in parsed.amount:
        amounts.extend(_normalize_ingredient_amount(amount))

    return Ingredient(
        id=ingredient_id,
        sentence=parsed.sentence,
        names=[item.text for item in parsed.name],
        amounts=amounts,
        size=_optional_text(parsed.size.text) if parsed.size else None,
        preparation=_optional_text(parsed.preparation.text)
        if parsed.preparation
        else None,
        comment=_optional_text(parsed.comment.text) if parsed.comment else None,
        purpose=_optional_text(parsed.purpose.text) if parsed.purpose else None,
    )


def _extract_direction_steps(recipe_instructions) -> list[tuple[str | None, str]]:
    steps = []

    if isinstance(recipe_instructions, str):
        text = recipe_instructions.strip()
        if text:
            steps.append((None, text))
        return steps

    if not isinstance(recipe_instructions, list):
        return steps

    for item in recipe_instructions:
        if isinstance(item, str):
            text = item.strip()
            if text:
                steps.append((None, text))
            continue

        if not isinstance(item, dict):
            continue

        if item.get("@type") == "HowToStep":
            text = item.get("text", "").strip()
            if text:
                steps.append((None, text))
            continue

        if item.get("@type") != "HowToSection":
            continue

        section_name = item.get("name")
        section = section_name.strip() if isinstance(section_name, str) else None
        for step in item.get("itemListElement", []):
            if isinstance(step, str):
                text = step.strip()
            elif isinstance(step, dict) and step.get("@type") == "HowToStep":
                text = step.get("text", "").strip()
            else:
                text = ""

            if text:
                steps.append((section, text))

    return steps


def _ingredient_name_aliases(name: str) -> list[str]:
    aliases = []
    candidate = name.strip()
    if not candidate:
        return aliases

    if candidate.lower() in _SUSPICIOUS_MATCHER_NAMES:
        return aliases

    aliases.append(candidate)
    words = candidate.split()

    if len(words) >= 3:
        aliases.append(" ".join(words[-2:]))

    if len(words) >= 2 and words[-1].lower() not in _BLOCKED_SINGLE_WORD_ALIASES:
        aliases.append(words[-1])

    return list(dict.fromkeys(alias for alias in aliases if alias))


def _previous_words(text: str, start: int, limit: int = 4) -> list[str]:
    return re.findall(r"[A-Za-z][A-Za-z'-]*", text[:start].lower())[-limit:]


def _next_word(text: str, end: int) -> str | None:
    match = re.match(r"\s*([A-Za-z][A-Za-z'-]*)", text[end:].lower())
    if not match:
        return None
    return match.group(1)


def _single_word_alias_has_explicit_context(text: str, start: int, end: int) -> bool:
    previous_words = _previous_words(text, start)
    next_word = _next_word(text, end)

    if previous_words and previous_words[-1] in _TRANSFORMED_INGREDIENT_WORDS:
        return False

    if next_word in _BLOCKED_ALIAS_EXTENSION_WORDS:
        return False

    if next_word in _PREPARATION_EXTENSION_WORDS:
        return True

    if previous_words and previous_words[-1] in _SINGLE_WORD_ALIAS_PREVIOUS_WORDS:
        return True

    if previous_words and any(
        word in _SINGLE_WORD_ALIAS_VERBS for word in previous_words
    ):
        return True

    if next_word is None or next_word in _SINGLE_WORD_ALIAS_NEXT_WORDS:
        return True

    return False


def _ingredient_match_candidates(
    ingredients: list[Ingredient],
) -> list[tuple[str, str, bool]]:
    candidates = []
    for ingredient in ingredients:
        for name in ingredient.names:
            for candidate in _ingredient_name_aliases(name):
                candidates.append(
                    (ingredient.id, candidate, len(candidate.split()) == 1)
                )

    return sorted(
        candidates,
        key=lambda item: (-len(item[1]), item[1].lower(), item[0]),
    )


def _ingredient_names_by_text(ingredients: list[Ingredient]) -> dict[str, str]:
    names_by_text = {}
    for ingredient in ingredients:
        for name in ingredient.names:
            normalized = " ".join(name.lower().split())
            if normalized:
                names_by_text[normalized] = ingredient.id
    return names_by_text


def _groupable_suffixes(ingredients: list[Ingredient]) -> set[str]:
    suffixes = set()
    for ingredient in ingredients:
        for name in ingredient.names:
            words = name.lower().split()
            if len(words) >= 2:
                suffixes.add(words[-1])
    return suffixes


def _parse_grouped_stems(value: str) -> list[str]:
    stems = [stem.strip().lower() for stem in re.split(r"\s*(?:,|\band\b)\s*", value)]
    return [stem for stem in stems if stem]


def _match_grouped_direction_ingredients(
    text: str, ingredients: list[Ingredient]
) -> tuple[list[tuple[int, int, list[str]]], list[tuple[str, int, int, list[str]]]]:
    matches = []
    grouped_references = []
    names_by_text = _ingredient_names_by_text(ingredients)

    for suffix in _groupable_suffixes(ingredients):
        pattern = re.compile(rf"(?<!\w){re.escape(suffix)}(?!\w)", re.IGNORECASE)
        for suffix_match in pattern.finditer(text):
            prefix = text[: suffix_match.start()]
            group_match = re.search(
                r"([A-Za-z][A-Za-z'-]*(?:\s*,\s*[A-Za-z][A-Za-z'-]*)+(?:\s+and\s+[A-Za-z][A-Za-z'-]*)?|[A-Za-z][A-Za-z'-]*(?:\s+and\s+[A-Za-z][A-Za-z'-]*)+)\s+$",
                prefix,
                re.IGNORECASE,
            )
            if not group_match:
                continue

            stems = _parse_grouped_stems(group_match.group(1))
            if len(stems) < 2:
                continue

            ids = []
            for stem in stems:
                ingredient_id = names_by_text.get(f"{stem} {suffix}".lower())
                if ingredient_id is None:
                    ids = []
                    break
                ids.append(ingredient_id)
            if not ids:
                continue

            start = group_match.start(1)
            end = suffix_match.end()
            matches.append((start, end, ids))
            grouped_references.append((suffix.lower(), start, end, ids))

    for suffix in _groupable_suffixes(ingredients):
        pattern = re.compile(rf"(?<!\w){re.escape(suffix)}(?!\w)", re.IGNORECASE)
        for match in pattern.finditer(text):
            start, end = match.span()
            if any(
                start >= existing_start and end <= existing_end
                for existing_start, existing_end, _ in matches
            ):
                continue
            ids = []
            for reference_suffix, _, reference_end, reference_ids in sorted(
                grouped_references, key=lambda item: item[1]
            ):
                if reference_suffix != suffix.lower() or reference_end >= start:
                    continue
                ids.extend(
                    ingredient_id
                    for ingredient_id in reference_ids
                    if ingredient_id not in ids
                )
            if not ids:
                continue
            matches.append((start, end, ids))

    return matches, grouped_references


def _is_unintroduced_group_suffix(
    candidate: str,
    start: int,
    grouped_references: list[tuple[str, int, int, list[str]]],
) -> bool:
    candidate = candidate.lower()
    same_suffix_references = [
        reference
        for reference in grouped_references
        if reference[0] == candidate
    ]
    if not same_suffix_references:
        return False

    has_prior_reference = any(
        reference_end < start for _, _, reference_end, _ in same_suffix_references
    )
    has_later_reference = any(
        reference_start > start for _, reference_start, _, _ in same_suffix_references
    )
    return has_later_reference and not has_prior_reference


def _extend_match_with_amount(
    text: str, start: int, ingredient: Ingredient
) -> int:
    best_start = start
    for amount_text in _ingredient_amount_aliases(ingredient):
        match = re.search(
            rf"(?<!\w){re.escape(amount_text)}\s+$",
            text[:start],
            re.IGNORECASE,
        )
        if match and match.start() < best_start:
            best_start = match.start()
    return best_start


def _ingredient_amount_aliases(ingredient: Ingredient) -> list[str]:
    aliases = []
    for amount in ingredient.amounts:
        amount_text = amount.text.strip()
        if amount_text:
            aliases.append(amount_text)

    lowered_sentence = ingredient.sentence.lower()
    for name in ingredient.names:
        lowered_name = name.lower()
        name_start = lowered_sentence.find(lowered_name)
        if name_start <= 0:
            continue

        amount_text = ingredient.sentence[:name_start].strip(" ,")
        if amount_text:
            aliases.append(amount_text)

    return list(dict.fromkeys(alias for alias in aliases if alias))


def _is_extended_single_word_alias(
    text: str,
    start: int,
    end: int,
    ingredient_id: str,
    candidate: str,
    ingredients: list[Ingredient],
) -> bool:
    if not _single_word_alias_has_explicit_context(text, start, end):
        return True

    next_match = re.match(r"\s+([A-Za-z]+)", text[end:])
    if not next_match:
        return False

    next_word = next_match.group(1).lower()
    if next_word not in _BLOCKED_ALIAS_EXTENSION_WORDS:
        return False

    extended_phrase = f"{candidate} {next_word}"
    for candidate_ingredient_id, known_candidate, _ in _ingredient_match_candidates(
        ingredients
    ):
        if candidate_ingredient_id != ingredient_id:
            continue
        if known_candidate.lower() == extended_phrase:
            return False

    return True


def _match_direction_ingredients(
    text: str, ingredients: list[Ingredient]
) -> list[tuple[int, int, list[str]]]:
    matches, grouped_references = _match_grouped_direction_ingredients(text, ingredients)
    occupied_ranges = [(start, end) for start, end, _ in matches]
    ingredient_lookup = {ingredient.id: ingredient for ingredient in ingredients}

    for ingredient_id, candidate, is_single_word_alias in _ingredient_match_candidates(
        ingredients
    ):
        pattern = re.compile(rf"(?<!\w){re.escape(candidate)}(?!\w)", re.IGNORECASE)
        for match in pattern.finditer(text):
            start, end = match.span()
            ingredient = ingredient_lookup[ingredient_id]
            start = _extend_match_with_amount(text, start, ingredient)
            if is_single_word_alias and _is_unintroduced_group_suffix(
                candidate, start, grouped_references
            ):
                continue
            if is_single_word_alias and _is_extended_single_word_alias(
                text, start, end, ingredient_id, candidate, ingredients
            ):
                continue
            if any(
                start < existing_end and end > existing_start
                for existing_start, existing_end in occupied_ranges
            ):
                continue
            matches.append((start, end, [ingredient_id]))
            occupied_ranges.append((start, end))

    matches.sort(key=lambda item: item[0])

    return matches


def _build_direction_highlights(
    text: str, ingredients: list[Ingredient]
) -> list[DirectionHighlight]:
    matches = _match_direction_ingredients(text, ingredients)
    highlights = []
    for start, end, ingredient_ids in matches:
        highlights.append(
            IngredientHighlight(
                type="ingredient",
                text=text[start:end],
                ids=ingredient_ids,
                start=start,
                end=end,
            )
        )

    return highlights


@dataclass
class Recipe:
    PROPERTY_FIELDS = [
        "name",
        "recipeIngredient",
        "recipeInstructions",
        "prepTime",
        "cookTime",
        "totalTime",
        "image",
        "thumbnailUrl",
        "video",
    ]
    _data: dict = Field(exclude=True)

    def __init__(self, data: dict) -> None:
        self._data = data

    @computed_field
    @property
    def title(self) -> str:
        return self._data.get("name", "")

    @computed_field
    @property
    def ingredients(self) -> list[Ingredient]:
        return [
            _normalize_ingredient(item, f"ingredient_{index}")
            for index, item in enumerate(self._data.get("recipeIngredient", []))
        ]

    @computed_field
    @property
    def directions(self) -> list[Direction]:
        ingredients = self.ingredients
        directions = []

        for index, (section, text) in enumerate(
            _extract_direction_steps(self._data.get("recipeInstructions", []))
        ):
            highlights = _build_direction_highlights(text, ingredients)
            directions.append(
                Direction(
                    id=f"step_{index}",
                    text=text,
                    section=section,
                    highlights=highlights,
                )
            )

        return directions

    @property
    def _prep_time_ms(self) -> int | None:
        return _parse_duration_ms(self._data.get("prepTime"))

    @property
    def _cook_time_ms(self) -> int | None:
        return _parse_duration_ms(self._data.get("cookTime"))

    @property
    def _total_time_ms(self) -> int | None:
        return _parse_duration_ms(self._data.get("totalTime"))

    @computed_field
    @property
    def time(self) -> RecipeTime | None:
        duration_ms = self._prep_time_ms or self._cook_time_ms or self._total_time_ms

        if self._prep_time_ms and self._cook_time_ms:
            duration_ms = self._prep_time_ms + self._cook_time_ms

        formatted_duration = _format_duration_ms(duration_ms)
        if duration_ms is None or formatted_duration is None:
            return None

        return RecipeTime(valueMs=duration_ms, valueFormatted=formatted_duration)

    @computed_field
    @property
    def video_url(self) -> str | None:
        return _video_url(self._data.get("video"))

    @computed_field
    @property
    def thumbnail_url(self) -> str | None:
        return (
            _thumbnail_url(self._data.get("thumbnailUrl"))
            or _image_url(self._data.get("image"))
            or _video_thumbnail_url(self._data.get("video"))
        )
