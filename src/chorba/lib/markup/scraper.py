from typing import Optional
import extruct
from curl_cffi import requests

from _schema_org import Recipe
from _processors import (
    SyntaxProcessor,
    JSONLDProcessor,
    MicrodataProcessor,
    RDFaProcessor,
)


class RecipeScraper:
    def __init__(self):
        self._processors: list[SyntaxProcessor] = [
            JSONLDProcessor(),
            MicrodataProcessor(),
            RDFaProcessor(),
        ]

    @property
    def syntax_names(self) -> list[str]:
        return [processor.syntax_name for processor in self._processors]

    def scrape_from_url(self, url: str) -> Optional[Recipe]:
        response = requests.get(url, impersonate="chrome")
        html = response.text

        extracted_data = extruct.extract(html, syntaxes=self.syntax_names)

        for processor in self._processors:
            if processor.syntax_name not in extracted_data:
                continue

            data = extracted_data.get(processor.syntax_name, [])
            recipe_data = processor.extract_recipe(data)

            if recipe_data:
                return Recipe(recipe_data)

        return None


if __name__ == "__main__":
    scraper = RecipeScraper()
    recipe = scraper.scrape_from_url("https://www.iankewks.com/classic-orange-chicken/")
    if not recipe:
        print("No recipe found")
    else:
        print(recipe.title)
        print(recipe.ingredients)
        print(recipe.directions)
