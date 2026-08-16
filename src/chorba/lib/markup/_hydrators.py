from dataclasses import dataclass
from html import unescape
import re
from typing import Protocol
import unicodedata

from parsel import Selector

from chorba.lib.markup._schema_org import Recipe


class HtmlRecipeHydrator(Protocol):
    def hydrate(self, recipe: Recipe, html: str) -> Recipe: ...


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
    aligned = []
    search_start = 0
    for ingredient in schema_ingredients:
        matches = []
        for index in range(search_start, len(candidates)):
            candidate = candidates[index]
            if _texts_match(ingredient, candidate.text_variants):
                matches.append((index, candidate))
        if len(matches) != 1:
            return None
        match_index, candidate = matches[0]
        aligned.append(candidate)
        search_start = match_index + 1
    return aligned


def _meaningful_heading_text(text: str) -> str | None:
    normalized = _normalize_match_text(text)
    if not normalized or normalized in _GENERIC_HEADINGS:
        return None
    return _SPACE_RE.sub(" ", unescape(text)).strip()


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


def _generic_section(candidate: _IngredientCandidate) -> str | None:
    heading_texts = candidate.selector.xpath(
        "ancestor::*[.//li][1]/preceding-sibling::*[self::h3 or self::h4 or self::h5 or self::h6][1]//text()"
    ).getall()
    if not heading_texts:
        heading_texts = candidate.selector.xpath(
            "preceding::*[self::h3 or self::h4 or self::h5 or self::h6][1]//text()"
        ).getall()
    if not heading_texts:
        return None
    return _meaningful_heading_text(" ".join(heading_texts))


def _candidate_section(candidate: _IngredientCandidate) -> str | None:
    return _group_section(candidate) or _generic_section(candidate)


class IngredientSectionHydrator:
    def hydrate(self, recipe: Recipe, html: str) -> Recipe:
        schema_ingredients = [ingredient.sentence for ingredient in recipe.ingredients]
        if not schema_ingredients:
            return recipe

        root = Selector(text=html)
        candidates = _ingredient_candidates(root)
        aligned = _align_ingredients(schema_ingredients, candidates)
        if aligned is None:
            return recipe

        return recipe.with_ingredient_sections(
            [_candidate_section(candidate) for candidate in aligned]
        )
