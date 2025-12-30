from typing import Optional
import json
from parsel import Selector
from recipe_scrapers import scrape_html
from curl_cffi import requests

from models import Ingredient, Recipe


def scrape_from_url(url: str) -> Recipe:
    html = fetch_html(url)
    return scrape(html, url)


def scrape(html: str, org_url: str) -> Recipe:
    selector = Selector(text=html)
    title: str = ""
    if site_title := selector.css("title::text").get():
        title = site_title
    ingredients = []
    directions = []

    if jsonld_scripts := selector.css(
        'script[type="application/ld+json"]::text'
    ).getall():
        jsonld_raw = merge_jsonld_scripts(jsonld_scripts)
        jsonld_data = try_parse_jsonld(jsonld_raw)
        title, ingredients, directions = extract_recipe_data(jsonld_data, title)
    elif microdata := selector.css(
        '[itemscope][itemtype="http://schema.org/Recipe"]'
    ).get():
        parsed_data = try_parse_microdata(Selector(text=microdata))
        title, ingredients, directions = extract_recipe_data(parsed_data, title)
    # TODO: remove recipe_scrapers fallback
    else:
        title, ingredients, directions = scrape_fallback(html, org_url, title)

    return Recipe(title=title, ingredients=ingredients, directions=directions)


def fetch_html(url: str) -> str:
    response = requests.get(url, impersonate="chrome")
    return response.text


def merge_jsonld_scripts(scripts):
    all_entities = []
    for script in scripts:
        try:
            data = json.loads(script)
            if isinstance(data, list):
                all_entities.extend(data)
            elif isinstance(data, dict):
                if "@graph" in data:
                    all_entities.extend(data["@graph"])
                else:
                    all_entities.append(data)
        except json.JSONDecodeError:
            continue

    return all_entities


def try_parse_jsonld(element) -> Optional[dict]:
    recipe_type = "Recipe"

    def is_recipe(item):
        if not isinstance(item, dict):
            return False
        t = item.get("@type")
        if isinstance(t, list):
            return recipe_type in t
        return t == recipe_type

    # Case 1: Element is a list of objects
    if isinstance(element, list):
        for d in element:
            if is_recipe(d):
                return d

    # Case 2: Element is a dictionary
    elif isinstance(element, dict):
        # Handle @graph nesting
        if "@graph" in element:
            graph = element["@graph"]
            if isinstance(graph, list):
                for node in graph:
                    if is_recipe(node):
                        return node

        # Handle direct match
        if is_recipe(element):
            return element

        # Handle nesting in mainEntity (common in Articles)
        main_entity = element.get("mainEntity")
        if isinstance(main_entity, dict) and is_recipe(main_entity):
            return main_entity


def try_parse_microdata(element) -> Optional[dict]:
    if not element.css("[itemscope]"):
        return None

    properties = {}
    for child in element.css("[itemprop]"):
        key = child.css("::attr(itemprop)").get()
        value = (
            try_parse_microdata(child)
            if child.css("[itemscope]")
            else child.css("::attr(content)").get() or child.css("::text").get()
        )
        properties[key] = value

    return {"properties": properties}


def scrape_fallback(html: str, url: str, title: str) -> tuple[str, list, list]:
    scraped_data = scrape_html(html, org_url=url).to_json()
    return (
        scraped_data.get("title", title),
        scraped_data.get("ingredients", []),
        scraped_data.get("instructions", []),
    )


# https://schema.org/Recipe
def extract_recipe_data(
    data: Optional[dict], fallback_title: str
) -> tuple[str, list[Ingredient], list[str]]:
    if not data:
        return fallback_title, [], []
    title = data.get("name", fallback_title)
    ingredients = [Ingredient(name=item) for item in data.get("recipeIngredient", [])]
    directions = extract_directions(data.get("recipeInstructions", []))
    return title, ingredients, directions


def extract_directions(instructions) -> list[str]:
    if not instructions:
        return []

    directions = []

    if isinstance(instructions, str):
        directions.append(instructions.strip())
    elif isinstance(instructions, list):
        for item in instructions:
            if isinstance(item, str):
                # String in array
                directions.append(item.strip())
            elif isinstance(item, dict):
                # HowToStep or HowToSection
                if item.get("@type") == "HowToStep":
                    text = item.get("text", "")
                    if text:
                        directions.append(text.strip())
                elif item.get("@type") == "HowToSection":
                    # HowToSection contains multiple steps
                    section_name = item.get("name", "")
                    if section_name:
                        directions.append(f"{section_name}:")

                    section_steps = item.get("itemListElement", [])
                    for step in section_steps:
                        if isinstance(step, dict) and step.get("@type") == "HowToStep":
                            text = step.get("text", "")
                            if text:
                                directions.append(f"  - {text.strip()}")
                        elif isinstance(step, str):
                            directions.append(f"  - {step.strip()}")

    return directions


if __name__ == "__main__":
    recipe = scrape_from_url("https://www.mob.co.uk/recipes/burnt-honey-teriyaki-udon")
    print(recipe)
