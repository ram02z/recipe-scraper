import json
from typing import Protocol

from parsel import Selector

from ._schema_org import Recipe


class IngredientSectionExtractor(Protocol):
    def extract(self, recipe: Recipe, html: str) -> list[str | None] | None: ...


class MobIngredientSectionExtractor:
    def extract(self, recipe: Recipe, html: str) -> list[str | None] | None:
        script = Selector(text=html).css("script#__NEXT_DATA__::text").get()
        if script is None:
            return None

        try:
            payload = json.loads(script)
            records = payload["props"]["pageProps"]["recipe"]["recipeIngredients"]
        except (json.JSONDecodeError, KeyError, TypeError):
            return None

        if not isinstance(records, list):
            return None

        active_section = None
        reconstructed = []
        sections = []
        for record in records:
            if not isinstance(record, dict):
                return None

            if record.get("typeHandle") == "header":
                heading = record.get("heading")
                if not isinstance(heading, str) or not heading.strip():
                    return None
                active_section = heading
                continue

            if record.get("typeHandle") != "ingredient":
                return None

            quantity = record.get("quantity")
            if quantity is not None and not isinstance(quantity, str):
                return None

            units = record.get("unit")
            ingredients = record.get("ingredient")
            if not isinstance(units, list) or not isinstance(ingredients, list):
                return None
            if not ingredients or not isinstance(ingredients[0], dict):
                return None

            title = ingredients[0].get("title")
            if not isinstance(title, str):
                return None

            unit_text = ""
            if units:
                if not isinstance(units[0], dict):
                    return None
                shorthand = units[0].get("shorthand")
                if shorthand is not None and not isinstance(shorthand, str):
                    return None
                unit_text = shorthand or units[0].get("title")
                if not isinstance(unit_text, str):
                    return None

            prefix = f"{quantity or ''}{unit_text}"
            reconstructed.append(f"{prefix} {title}" if prefix else title)
            sections.append(active_section)

        schema_ingredients = [ingredient.sentence for ingredient in recipe.ingredients]
        if reconstructed != schema_ingredients:
            return None
        return sections


DEFAULT_INGREDIENT_SECTION_EXTRACTORS: dict[str, IngredientSectionExtractor] = {
    "www.mob.co.uk": MobIngredientSectionExtractor()
}
