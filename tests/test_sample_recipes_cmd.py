import random

from chorba.cmd import sample_recipes
from chorba.lib.markup._schema_org import Recipe


def test_parse_hosts_defaults_to_supported_hosts():
    assert sample_recipes.parse_hosts(None) == sample_recipes.get_supported_hosts()


def test_seed_url_uses_host_specific_overrides():
    assert sample_recipes.seed_url_for_host("bbc.co.uk") == "https://www.bbc.co.uk/food"
    assert sample_recipes.seed_url_for_host("food52.com") == "https://www.food52.com/"


def test_sitemap_candidates_include_direct_host_variants():
    assert sample_recipes.sitemap_candidates_for_host("bbc.co.uk") == [
        "https://www.bbc.co.uk/food/sitemap.xml",
        "https://bbc.co.uk/sitemap.xml",
        "https://www.bbc.co.uk/sitemap.xml",
    ]


def test_sample_urls_is_reproducible():
    urls = [f"https://example.com/{index}" for index in range(10)]

    first = sample_recipes.sample_urls(urls, 3, random.Random(42))
    second = sample_recipes.sample_urls(urls, 3, random.Random(42))

    assert first == second
    assert len(first) == 3


def test_serialize_recipe_uses_api_shape():
    recipe = Recipe(
        {
            "name": "Test",
            "recipeIngredient": ["1 onion, sliced"],
            "recipeInstructions": ["Cook the onion."],
            "prepTime": "PT10M",
        }
    )

    assert sample_recipes.serialize_recipe(recipe) == {
        "title": "Test",
        "ingredients": [
            {
                "id": "ingredient_0",
                "sentence": "1 onion, sliced",
                "names": ["onion"],
                "amounts": [
                    {
                        "quantity": "1",
                        "quantity_max": "1",
                        "unit": None,
                        "text": "1",
                    }
                ],
                "size": None,
                "preparation": "sliced",
                "comment": None,
                "purpose": None,
            }
        ],
        "directions": [
            {
                "id": "step_0",
                "text": "Cook the onion.",
                "section": None,
                "highlights": [
                    {
                        "type": "ingredient",
                        "text": "onion",
                        "ids": ["ingredient_0"],
                        "start": 9,
                        "end": 14,
                    },
                ],
            }
        ],
        "time": {"valueMs": 600000, "valueFormatted": "10 min"},
        "video_url": None,
        "thumbnail_url": None,
    }


def test_build_record_contains_sampling_metadata():
    recipe = Recipe({"name": "Test", "recipeIngredient": [], "recipeInstructions": []})

    record = sample_recipes.build_record(
        host="example.com",
        sitemap="https://example.com/sitemap.xml",
        crawl_delay=1,
        seed=42,
        sample_index=3,
        url="https://example.com/recipe/test",
        recipe=recipe,
        error=None,
    )

    assert record["host"] == "example.com"
    assert record["sample_index"] == 3
    assert record["scrape_ok"] is True
    assert record["recipe_found"] is True
    assert record["recipe"]["title"] == "Test"


def test_resolve_sitemap_url_uses_direct_fallback(monkeypatch):
    class FakeRobotFileManager:
        def __init__(self, url: str):
            self.sitemap = None
            self.crawl_delay = 3

    class FakeResponse:
        def raise_for_status(self):
            return None

    class FakeRequests:
        @staticmethod
        def get(url: str, impersonate: str, timeout: int):
            if url == "https://food52.com/sitemap.xml":
                return FakeResponse()
            raise RuntimeError("not found")

    monkeypatch.setattr(sample_recipes, "RobotFileManager", FakeRobotFileManager)
    monkeypatch.setattr(sample_recipes, "requests", FakeRequests)

    sitemap, crawl_delay = sample_recipes.resolve_sitemap_url("food52.com")

    assert sitemap == "https://food52.com/sitemap.xml"
    assert crawl_delay == 3


def test_discover_recipe_urls_filters_and_dedupes(monkeypatch):
    class FakeRobotFileManager:
        def __init__(self, url: str):
            self.sitemap = "https://example.com/sitemap.xml"
            self.crawl_delay = 2

        def filter_urls(self, urls: list[str]) -> list[str]:
            return [url for url in urls if "keep" in url]

    class FakeParser:
        async def get_recipe_urls(self) -> list[str]:
            return [
                "https://example.com/keep-a",
                "https://example.com/drop-b",
                "https://example.com/keep-a",
                "https://example.com/keep-c",
            ]

    class FakeFactory:
        @staticmethod
        def from_xml_url(url: str):
            return FakeParser()

    monkeypatch.setattr(sample_recipes, "RobotFileManager", FakeRobotFileManager)
    monkeypatch.setattr(sample_recipes, "SitemapParserFactory", FakeFactory)

    sitemap, crawl_delay, urls = sample_recipes.asyncio.run(
        sample_recipes.discover_recipe_urls("example.com")
    )

    assert sitemap == "https://example.com/sitemap.xml"
    assert crawl_delay == 2
    assert urls == [
        "https://example.com/keep-a",
        "https://example.com/keep-c",
    ]
