from abc import ABC, abstractmethod

from chorba.lib.markup._schema_org import Recipe


def _has_type(item: dict, schema_type: str) -> bool:
    if not isinstance(item, dict):
        return False

    item_type = item.get("@type") or item.get("type", "")
    if isinstance(item_type, list):
        return schema_type in item_type or any(schema_type in t for t in item_type)
    return item_type == schema_type or schema_type in item_type


def _jsonld_nodes(data: list[dict]) -> list[dict]:
    nodes = []

    for item in data:
        if not isinstance(item, dict):
            continue

        nodes.append(item)

        graph = item.get("@graph", [])
        if isinstance(graph, list):
            nodes.extend(node for node in graph if isinstance(node, dict))

    return nodes


def _single_video_candidate(candidates: list[dict]) -> dict:
    if len(candidates) == 1:
        return candidates[0]
    return {}


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
        nodes = _jsonld_nodes(data)

        def is_recipe(item: dict) -> bool:
            return _has_type(item, "Recipe")

        video_candidates = [item for item in nodes if _has_type(item, "VideoObject")]

        for item in nodes:
            if is_recipe(item):
                if not item.get("video"):
                    maybe_video = _single_video_candidate(video_candidates)
                    if maybe_video:
                        item = {**item, "video": maybe_video}
                return item

        return {}


class MicrodataProcessor(SyntaxProcessor):
    @property
    def syntax_name(self) -> str:
        return "microdata"

    def extract_recipe(self, data: list[dict]) -> dict:
        video_candidates = []

        for d in data:
            data_type = d.get("type", "")
            if "schema.org/VideoObject" in data_type:
                video_candidates.append(d.get("properties", {}))
            if "schema.org/Recipe" in data_type:
                recipe = d.get("properties", {})
                if not recipe.get("video"):
                    maybe_video = _single_video_candidate(video_candidates)
                    if maybe_video:
                        recipe = {**recipe, "video": maybe_video}
                return recipe
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

        video_candidates = []
        for item in data:
            if _has_type(item, "VideoObject"):
                resolved_video = {}
                for prop in [
                    "contentUrl",
                    "embedUrl",
                    "url",
                    "thumbnailUrl",
                    "thumbnail",
                ]:
                    value = extract_property(item, prop)
                    if value is not None:
                        resolved_video[prop] = value
                if resolved_video:
                    video_candidates.append(resolved_video)

        recipe_properties = Recipe.PROPERTY_FIELDS
        uniform_recipe = {}
        for prop in recipe_properties:
            value = extract_property(recipe, prop)
            if value is not None:
                uniform_recipe[prop] = value

        if not uniform_recipe.get("video"):
            maybe_video = _single_video_candidate(video_candidates)
            if maybe_video:
                uniform_recipe["video"] = maybe_video

        return uniform_recipe
