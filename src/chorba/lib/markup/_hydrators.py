from dataclasses import dataclass
from html import unescape
import re
from typing import Protocol
import unicodedata
from urllib.parse import urlparse

from parsel import Selector

from chorba.lib.markup._section_extractors import (
    DEFAULT_INGREDIENT_SECTION_EXTRACTORS,
    IngredientSectionExtractor,
)
from chorba.lib.markup._schema_org import Recipe


class HtmlRecipeHydrator(Protocol):
    def hydrate(
        self, recipe: Recipe, html: str, url: str | None = None
    ) -> Recipe: ...


@dataclass
class _IngredientCandidate:
    selector: Selector
    order: int
    text_variants: list[str]


_CHECKBOX_MARKERS = {"\u25a2", "\u2610", "\u2611", "\u2612"}
_QUOTE_TRANSLATION = str.maketrans({"“": '"', "”": '"', "‘": "'", "’": "'"})
_DASH_RE = re.compile(r"[\u2010\u2011\u2012\u2013\u2014\u2212]")
_SPACE_RE = re.compile(r"\s+")
_PUNCT_RE = re.compile(r"[^\w\s/.-]")
_GENERIC_HEADINGS = {"ingredient", "ingredients"}


def _normalize_match_text(text: str) -> str:
    text = unescape(text)
    text = unicodedata.normalize("NFKC", text)
    text = text.translate(_QUOTE_TRANSLATION)
    text = _DASH_RE.sub("-", text)
    for marker in _CHECKBOX_MARKERS:
        text = text.replace(marker, " ")
    text = text.replace("\xa0", " ")
    text = _SPACE_RE.sub(" ", text)
    return text.strip().lower()


def _match_key(text: str) -> str:
    text = _normalize_match_text(text)
    text = text.replace("(", " ").replace(")", " ").replace(",", " ")
    text = _PUNCT_RE.sub(" ", text)
    text = _SPACE_RE.sub(" ", text)
    return text.strip()


def _texts_match(schema_text: str, candidate_texts: list[str]) -> bool:
    schema_key = _match_key(schema_text)
    return any(_match_key(candidate_text) == schema_key for candidate_text in candidate_texts)


def _element_text(selector: Selector) -> str:
    return " ".join(selector.xpath(".//text()").getall())


def _wprm_component_text(selector: Selector) -> str | None:
    parts = []
    for css_class in [
        ".wprm-recipe-ingredient-amount",
        ".wprm-recipe-ingredient-unit",
        ".wprm-recipe-ingredient-name",
        ".wprm-recipe-ingredient-notes",
    ]:
        text = " ".join(selector.css(f"{css_class}::text").getall()).strip()
        if text:
            parts.append(text)
    if not parts:
        return None
    return " ".join(parts)


def _ingredient_candidates(root: Selector) -> list[_IngredientCandidate]:
    candidates = []
    for order, item in enumerate(root.css("li")):
        variants = [_element_text(item)]
        aria_label = item.attrib.get("aria-label")
        if aria_label:
            variants.append(aria_label)
        component_text = _wprm_component_text(item)
        if component_text:
            variants.append(component_text)
        variants = [variant for variant in variants if _normalize_match_text(variant)]
        if variants:
            candidates.append(
                _IngredientCandidate(
                    selector=item,
                    order=order,
                    text_variants=variants,
                )
            )
    return candidates


def _align_ingredients(
    schema_ingredients: list[str], candidates: list[_IngredientCandidate]
) -> list[_IngredientCandidate] | None:
    matching_indices = [
        {
            index
            for index, candidate in enumerate(candidates)
            if _texts_match(ingredient, candidate.text_variants)
        }
        for ingredient in schema_ingredients
    ]

    ingredient_count = len(schema_ingredients)
    candidate_count = len(candidates)
    alignment_counts = [
        bytearray(candidate_count + 1) for _ in range(ingredient_count + 1)
    ]
    alignment_counts[ingredient_count] = bytearray([1]) * (candidate_count + 1)

    for ingredient_index in range(ingredient_count - 1, -1, -1):
        row = alignment_counts[ingredient_index]
        next_row = alignment_counts[ingredient_index + 1]
        matches = matching_indices[ingredient_index]
        for candidate_index in range(candidate_count - 1, -1, -1):
            count = row[candidate_index + 1]
            if candidate_index in matches:
                count += next_row[candidate_index + 1]
            row[candidate_index] = min(2, count)

    if alignment_counts[0][0] != 1:
        return None

    path = []
    ingredient_index = 0
    candidate_index = 0
    while ingredient_index < ingredient_count:
        matches = matching_indices[ingredient_index]
        take_count = (
            alignment_counts[ingredient_index + 1][candidate_index + 1]
            if candidate_index in matches
            else 0
        )
        skip_count = alignment_counts[ingredient_index][candidate_index + 1]
        if take_count == 1 and skip_count == 0:
            path.append(candidate_index)
            ingredient_index += 1
        candidate_index += 1

    return [candidates[index] for index in path]


def _meaningful_heading_text(text: str) -> str | None:
    if not _heading_key(text) or _is_ingredient_anchor(text):
        return None
    return _SPACE_RE.sub(" ", unescape(text)).strip()


def _heading_key(text: str) -> str:
    normalized = _normalize_match_text(text)
    start = 0
    end = len(normalized)
    while start < end and unicodedata.category(normalized[start]).startswith("P"):
        start += 1
    while end > start and unicodedata.category(normalized[end - 1]).startswith("P"):
        end -= 1
    return normalized[start:end].strip()


def _is_ingredient_anchor(text: str) -> bool:
    return _heading_key(text) in _GENERIC_HEADINGS


def _group_section(candidate: _IngredientCandidate) -> str | None:
    group_heading = candidate.selector.xpath(
        "ancestor::*[contains(concat(' ', normalize-space(@class), ' '), "
        "' wprm-recipe-ingredient-group ')][1]"
        "//*[contains(concat(' ', normalize-space(@class), ' '), "
        "' wprm-recipe-ingredient-group-name ')]//text()"
    ).getall()
    if not group_heading:
        return None
    return _meaningful_heading_text(" ".join(group_heading))


def _ingredient_scope(aligned: list[_IngredientCandidate]) -> Selector | None:
    if not aligned:
        return None

    lineages = [
        [candidate.selector.root, *candidate.selector.root.iterancestors()]
        for candidate in aligned
    ]
    for element in lineages[0]:
        if all(element in lineage for lineage in lineages[1:]):
            return Selector(root=element)
    return None


def _is_heading(element) -> bool:
    return isinstance(element.tag, str) and element.tag.lower() in {
        "h1",
        "h2",
        "h3",
        "h4",
        "h5",
        "h6",
    }


def _element_descendant_text(element) -> str:
    return " ".join(element.itertext())


def _generic_sections(
    aligned: list[_IngredientCandidate], scope: Selector | None
) -> list[str | None]:
    sections: list[str | None] = [None] * len(aligned)
    if scope is None or not isinstance(scope.root.tag, str):
        return sections
    if scope.root.tag.lower() in {"html", "body"}:
        return sections

    candidate_indices = {
        candidate.selector.root: index for index, candidate in enumerate(aligned)
    }
    first_candidate = aligned[0].selector.root
    anchor = None
    for element in scope.root.iter():
        if element is first_candidate:
            break
        if _is_heading(element) and _is_ingredient_anchor(
            _element_descendant_text(element)
        ):
            anchor = element

    active_section = None
    headings_are_eligible = anchor is None
    for element in scope.root.iter():
        if _is_heading(element):
            heading_text = _element_descendant_text(element)
            if element is anchor:
                headings_are_eligible = True
                active_section = None
            elif headings_are_eligible:
                active_section = _meaningful_heading_text(heading_text)

        candidate_index = candidate_indices.get(element)
        if candidate_index is not None:
            sections[candidate_index] = active_section

    return sections



class IngredientSectionHydrator:
    def __init__(
        self,
        ingredient_section_extractors: dict[str, IngredientSectionExtractor] | None = None,
    ):
        self._ingredient_section_extractors = (
            DEFAULT_INGREDIENT_SECTION_EXTRACTORS
            if ingredient_section_extractors is None
            else ingredient_section_extractors
        )

    def hydrate(
        self, recipe: Recipe, html: str, url: str | None = None
    ) -> Recipe:
        schema_ingredients = [ingredient.sentence for ingredient in recipe.ingredients]
        try:
            hostname = urlparse(url).hostname if url else None
        except ValueError:
            hostname = None
        extractor = (
            self._ingredient_section_extractors.get(hostname)
            if hostname is not None
            else None
        )
        if extractor is not None:
            try:
                sections = extractor.extract(recipe, html)
            except Exception:
                sections = None
            if (
                isinstance(sections, list)
                and len(sections) == len(schema_ingredients)
                and all(section is None or isinstance(section, str) for section in sections)
            ):
                return recipe.with_ingredient_sections(sections)

        if not schema_ingredients:
            return recipe

        root = Selector(text=html)
        candidates = _ingredient_candidates(root)
        aligned = _align_ingredients(schema_ingredients, candidates)
        if aligned is None:
            return recipe

        generic_sections = _generic_sections(aligned, _ingredient_scope(aligned))
        return recipe.with_ingredient_sections(
            [
                _group_section(candidate) or generic_sections[index]
                for index, candidate in enumerate(aligned)
            ]
        )
