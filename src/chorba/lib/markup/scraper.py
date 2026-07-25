from typing import Optional
import extruct
from curl_cffi import requests

from chorba.lib.markup._schema_org import Recipe
from chorba.lib.markup._processors import (
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
        response.raise_for_status()
        html = response.text

        return self.scrape(html)

    def scrape(self, html: str) -> Optional[Recipe]:
        extracted_data = extruct.extract(html, syntaxes=self.syntax_names)

        for processor in self._processors:
            if processor.syntax_name not in extracted_data:
                continue

            data = extracted_data.get(processor.syntax_name)
            if not data:
                continue
            recipe_data = processor.extract_recipe(data)

            if recipe_data:
                return Recipe(recipe_data)

        return None
