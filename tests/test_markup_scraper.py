import pytest
from curl_cffi import requests

from chorba.lib.markup import scraper
from chorba.lib.markup import _schema_org


class ErrorResponse:
    text = "<html></html>"

    def raise_for_status(self):
        raise requests.RequestsError("HTTP Error 404", response=self)


def test_scrape_from_url_raises_for_http_status(monkeypatch):
    monkeypatch.setattr(scraper.requests, "get", lambda *args, **kwargs: ErrorResponse())

    with pytest.raises(requests.RequestsError):
        scraper.RecipeScraper().scrape_from_url("https://example.com/missing")


class FakeProcessor:
    @property
    def syntax_name(self):
        return "json-ld"

    def extract_recipe(self, data):
        return {"name": "Test", "recipeIngredient": ["1 cup rice"]}


class FakeHydrator:
    def __init__(self):
        self.calls = []

    def hydrate(self, recipe, html, url=None):
        self.calls.append((recipe, html, url))
        return recipe.with_ingredient_sections(["Rice"])


def test_scrape_passes_recipe_and_raw_html_to_hydrators():
    hydrator = FakeHydrator()
    recipe = scraper.RecipeScraper(
        processors=[FakeProcessor()],
        hydrators=[hydrator],
    ).scrape('<script type="application/ld+json">{"@type":"Recipe"}</script>')

    assert recipe is not None
    assert len(hydrator.calls) == 1
    hydrated_recipe, raw_html, url = hydrator.calls[0]
    assert hydrated_recipe.title == "Test"
    assert [ingredient.sentence for ingredient in hydrated_recipe.ingredients] == [
        "1 cup rice"
    ]
    assert raw_html == '<script type="application/ld+json">{"@type":"Recipe"}</script>'
    assert url is None
    assert recipe.ingredients[0].section == "Rice"


class RaisingHydrator:
    def hydrate(self, recipe, html, url=None):
        raise RuntimeError("boom")


class ReplacingHydrator:
    def __init__(self, section):
        self.section = section
        self.calls = []

    def hydrate(self, recipe, html, url=None):
        self.calls.append((recipe, html, url))
        return recipe.with_ingredient_sections([self.section])


def test_scrape_ignores_hydrator_exceptions():
    recipe = scraper.RecipeScraper(
        processors=[FakeProcessor()],
        hydrators=[RaisingHydrator()],
    ).scrape('<script type="application/ld+json">{"@type":"Recipe"}</script>')

    assert recipe is not None
    assert recipe.ingredients[0].section is None


def test_scrape_preserves_prior_hydration_when_later_hydrator_raises():
    recipe = scraper.RecipeScraper(
        processors=[FakeProcessor()],
        hydrators=[FakeHydrator(), RaisingHydrator()],
    ).scrape('<script type="application/ld+json">{"@type":"Recipe"}</script>')

    assert recipe is not None
    assert recipe.ingredients[0].section == "Rice"


def test_scrape_passes_replacement_recipe_to_next_successful_hydrator():
    first = ReplacingHydrator("First")
    second = ReplacingHydrator("Second")

    recipe = scraper.RecipeScraper(
        processors=[FakeProcessor()],
        hydrators=[first, second],
    ).scrape('<script type="application/ld+json">{"@type":"Recipe"}</script>')

    assert recipe is not None
    assert second.calls[0][0].ingredients[0].section == "First"
    assert recipe.ingredients[0].section == "Second"


def test_scrape_passes_url_context_to_hydrators():
    hydrator = FakeHydrator()
    html = '<script type="application/ld+json">{"@type":"Recipe"}</script>'
    url = "https://www.example.com:8443/recipes/rice?serves=4"

    recipe = scraper.RecipeScraper(
        processors=[FakeProcessor()],
        hydrators=[hydrator],
    ).scrape(html, url)

    assert recipe is not None
    assert recipe.ingredients[0].section == "Rice"
    assert len(hydrator.calls) == 1
    hydrated_recipe, raw_html, hydrated_url = hydrator.calls[0]
    assert hydrated_recipe.title == "Test"
    assert raw_html == html
    assert hydrated_url == url


class RedirectedResponse:
    text = '<script type="application/ld+json">{"@type":"Recipe"}</script>'
    url = "https://www.example.com/final"

    def raise_for_status(self):
        pass


def test_scrape_from_url_passes_final_response_url_to_hydrators(monkeypatch):
    monkeypatch.setattr(
        scraper.requests,
        "get",
        lambda *args, **kwargs: RedirectedResponse(),
    )
    hydrator = FakeHydrator()

    recipe = scraper.RecipeScraper(
        processors=[FakeProcessor()],
        hydrators=[hydrator],
    ).scrape_from_url("https://redirect.example/start")

    assert recipe is not None
    assert recipe.ingredients[0].section == "Rice"
    assert len(hydrator.calls) == 1
    assert hydrator.calls[0][2] == "https://www.example.com/final"
