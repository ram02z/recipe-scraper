from abc import ABC, abstractmethod

from chorba.lib.markup._schema_org import Recipe


class SyntaxProcessor(ABC):
    @property
    @abstractmethod
    def syntax_name(self) -> str:
        """Return the syntax name used by extruct.extract()."""
        pass

    @abstractmethod
    def extract_recipe(self, data: list[dict]) -> dict:
        """Extract recipe data from the parsed syntax data."""
        pass


class JSONLDProcessor(SyntaxProcessor):
    @property
    def syntax_name(self) -> str:
        return "json-ld"

    def extract_recipe(self, data: list[dict]) -> dict:
        context = "schema.org"
        recipe_type = "Recipe"

        def is_recipe(item: dict) -> bool:
            if not isinstance(item, dict):
                return False
            c = item.get("@context", "")
            if context not in c:
                return False
            t = item.get("@type", "")
            if isinstance(t, list):
                return recipe_type in t
            return t == recipe_type

        for item in data:
            if is_recipe(item):
                return item

        return {}


class MicrodataProcessor(SyntaxProcessor):
    @property
    def syntax_name(self) -> str:
        return "microdata"

    def extract_recipe(self, data: list[dict]) -> dict:
        for d in data:
            data_type = d.get("type", "")
            if "schema.org/Recipe" in data_type:
                return d.get("properties", {})
        return {}


class RDFaProcessor(SyntaxProcessor):
    @property
    def syntax_name(self) -> str:
        return "rdfa"

    def extract_recipe(self, data: list[dict]) -> dict:
        node_lookup = {item["@id"]: item for item in data if "@id" in item}

        recipe = None
        for item in data:
            if "@type" in item and any("Recipe" in t for t in item.get("@type", [])):
                recipe = item
                break

        if not recipe:
            return {}

        def resolve_value(data) -> dict | list[str] | str | None:
            if isinstance(data, list):
                resolved_items = []
                for item in data:
                    resolved = resolve_value(item)
                    if resolved is not None:
                        resolved_items.append(resolved)

                if len(resolved_items) == 0:
                    return None
                elif len(resolved_items) == 1:
                    return resolved_items[0]
                else:
                    return resolved_items

            if isinstance(data, dict):
                if "@value" in data:
                    return data["@value"]

                if "@id" in data:
                    node_id = data["@id"]

                    if node_id.startswith("http://") or node_id.startswith("https://"):
                        return node_id

                    referenced_node = node_lookup.get(node_id)
                    if referenced_node:
                        resolved_node = {}
                        for key, value in referenced_node.items():
                            if "schema.org" in key:
                                prop_name = key.split("/")[-1]
                                resolved_node[prop_name] = resolve_value(value)

                        if len(resolved_node) == 1:
                            return next(iter(resolved_node.values()))
                        elif resolved_node:
                            return resolved_node

                    return node_id

                result = {}
                for key, value in data.items():
                    if not key.startswith("@"):
                        resolved = resolve_value(value)
                        if resolved is not None:
                            result[key] = resolved
                return result

            return data

        def extract_property(recipe_data: dict, schema_property: str):
            for protocol in ["https://", "http://"]:
                full_property = f"{protocol}schema.org/{schema_property}"
                if full_property in recipe_data:
                    return resolve_value(recipe_data[full_property])

            return None

        recipe_properties = Recipe.PROPERTY_FIELDS
        uniform_recipe = {}
        for prop in recipe_properties:
            value = extract_property(recipe, prop)
            if value is not None:
                uniform_recipe[prop] = value

        return uniform_recipe
