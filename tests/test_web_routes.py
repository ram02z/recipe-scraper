from fastapi.testclient import TestClient
from curl_cffi import requests

from chorba.cmd.server import create_app
from chorba.web import routes


class FakeResponse:
    def __init__(self, status_code: int):
        self.status_code = status_code


class EmptyRecipeScraper:
    def scrape_from_url(self, url: str):
        return None


class NotFoundRecipeScraper:
    def scrape_from_url(self, url: str):
        raise requests.RequestsError("HTTP Error 404", response=FakeResponse(404))


def test_recipe_endpoint_returns_422_when_recipe_cannot_be_parsed(monkeypatch):
    monkeypatch.setattr(routes, "recipe_scraper", EmptyRecipeScraper())

    response = TestClient(create_app()).get("/recipe?url=https://example.com/page")

    assert response.status_code == 422


def test_recipe_endpoint_returns_404_when_recipe_url_is_not_found(monkeypatch):
    monkeypatch.setattr(routes, "recipe_scraper", NotFoundRecipeScraper())

    response = TestClient(create_app()).get("/recipe?url=https://example.com/missing")

    assert response.status_code == 404


def test_recipe_response_schema_requires_recipe():
    openapi = create_app().openapi()
    recipe_response_schema = openapi["components"]["schemas"]["RecipeResponse"]

    assert recipe_response_schema["required"] == ["recipe"]
    assert recipe_response_schema["properties"]["recipe"] == {
        "$ref": "#/components/schemas/Recipe"
    }
