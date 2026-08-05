import json
import logging

import pytest
from curl_cffi import requests
from fastapi.testclient import TestClient
from starlette.requests import Request

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


class FakeReportRepository:
    def __init__(self):
        self.user_reports = []
        self.parse_failures = []

    async def create_user_report(self, report):
        self.user_reports.append(report)

    async def create_parse_failure(self, recipe_url, api_version, user_agent):
        self.parse_failures.append(
            {
                "recipe_url": recipe_url,
                "api_version": api_version,
                "user_agent": user_agent,
            }
        )


class FailingReportRepository:
    async def create_user_report(self, report):
        from chorba.web.reports import RecipeReportUnavailable

        raise RecipeReportUnavailable

    async def create_parse_failure(self, recipe_url, api_version, user_agent):
        from chorba.web.reports import RecipeReportUnavailable

        raise RecipeReportUnavailable


class UnexpectedFailingReportRepository:
    async def create_parse_failure(self, recipe_url, api_version, user_agent):
        raise RuntimeError("unexpected persistence failure")


def create_test_app(repository=None, api_version="test-api"):
    from chorba.config import Settings

    return create_app(
        settings=Settings(
            database_url="postgresql://postgres:postgres@127.0.0.1:54322/postgres",
            api_version=api_version,
        ),
        report_repository=repository,
    )


def request(method, app, url, **kwargs):
    with TestClient(app) as client:
        return client.request(method, url, **kwargs)


def test_health_endpoint_returns_status_and_api_version():
    response = request("GET", create_test_app(api_version="0.1.0-abcdef0"), "/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "api_version": "0.1.0-abcdef0"}


def test_recipe_endpoint_returns_422_when_recipe_cannot_be_parsed(monkeypatch):
    monkeypatch.setattr(routes, "recipe_scraper", EmptyRecipeScraper())

    response = request("GET", create_test_app(), "/recipe?url=https://example.com/page")

    assert response.status_code == 422


def test_recipe_endpoint_returns_404_when_recipe_url_is_not_found(monkeypatch):
    monkeypatch.setattr(routes, "recipe_scraper", NotFoundRecipeScraper())

    response = request(
        "GET", create_test_app(), "/recipe?url=https://example.com/missing"
    )

    assert response.status_code == 404


def test_recipe_response_schema_requires_recipe():
    openapi = create_app().openapi()
    recipe_response_schema = openapi["components"]["schemas"]["RecipeResponse"]

    assert recipe_response_schema["required"] == ["recipe"]
    assert recipe_response_schema["properties"]["recipe"] == {
        "$ref": "#/components/schemas/Recipe"
    }


def test_report_category_openapi_schema_is_named_string_enum():
    openapi = create_app().openapi()
    schemas = openapi["components"]["schemas"]

    assert schemas["RecipeReportRequest"]["properties"]["categories"]["items"] == {
        "$ref": "#/components/schemas/UserReportCategory"
    }
    assert schemas["UserReportCategory"]["type"] == "string"
    assert schemas["UserReportCategory"]["enum"] == [
        "ingredient_parsing",
        "directions",
        "media",
        "metadata",
        "rendering",
        "other",
    ]


def test_report_request_openapi_schema_documents_semantic_constraints():
    schemas = create_app().openapi()["components"]["schemas"]
    properties = schemas["RecipeReportRequest"]["properties"]

    assert properties["recipe_url"]["description"] == (
        "HTTP or HTTPS URL, limited to 2048 bytes when UTF-8 encoded."
    )
    assert properties["categories"]["minItems"] == 1
    assert properties["categories"]["maxItems"] == 6
    assert properties["categories"]["uniqueItems"] is True
    assert properties["note"]["anyOf"][0]["maxLength"] == 4000
    assert properties["note"]["description"] == (
        "Optional note; trimmed of surrounding whitespace, with blank values "
        "normalized to null; required when categories includes 'other'."
    )
    assert properties["recipe_snapshot"]["type"] == "object"
    assert properties["recipe_snapshot"]["description"] == (
        "JSON object whose compact UTF-8 serialization is at most 128 KiB."
    )
    assert properties["client_version"]["minLength"] == 1
    assert properties["client_version"]["maxLength"] == 128
    assert properties["client_version"]["description"] == (
        "Client version; trimmed of surrounding whitespace and must be nonblank."
    )


def test_report_endpoint_openapi_uses_fastapi_validation_response_schema():
    openapi = create_app().openapi()
    responses = openapi["paths"]["/recipe/report"]["post"]["responses"]

    assert set(responses) == {"204", "422"}
    assert responses["204"]["description"] == "Successful Response"
    validation_content = responses["422"]["content"]["application/json"]
    assert validation_content["schema"] == {
        "$ref": "#/components/schemas/HTTPValidationError"
    }
    assert "examples" not in validation_content

    validation_error = openapi["components"]["schemas"]["ValidationError"]
    assert set(validation_error["required"]) == {"loc", "msg", "type"}
    assert validation_error["properties"]["loc"]["items"]["anyOf"] == [
        {"type": "string"},
        {"type": "integer"},
    ]


def test_report_endpoint_persists_valid_user_report():
    repository = FakeReportRepository()

    response = request(
        "POST",
        create_test_app(repository),
        "/recipe/report",
        headers={"User-Agent": "chorba-test"},
        json={
            "recipe_url": "https://example.com/recipe",
            "categories": ["ingredient_parsing"],
            "note": "Incorrect quantity",
            "recipe_snapshot": {"title": "Example"},
            "client_version": "test-client",
        },
    )

    assert response.status_code == 204
    assert response.content == b""
    assert len(repository.user_reports) == 1
    report = repository.user_reports[0]
    assert report.recipe_url == "https://example.com/recipe"
    assert report.categories == ["ingredient_parsing"]
    assert report.note == "Incorrect quantity"
    assert report.recipe_snapshot == {"title": "Example"}
    assert report.client_version == "test-client"
    assert report.api_version == "test-api"
    assert report.user_agent == "chorba-test"


def test_report_endpoint_persists_categories_as_plain_strings():
    repository = FakeReportRepository()

    response = request(
        "POST",
        create_test_app(repository),
        "/recipe/report",
        json={
            "recipe_url": "https://example.com/recipe",
            "categories": ["directions", "media"],
            "recipe_snapshot": {"title": "Example"},
            "client_version": "test-client",
        },
    )

    assert response.status_code == 204
    assert repository.user_reports[0].categories == ["directions", "media"]
    assert all(type(category) is str for category in repository.user_reports[0].categories)


def test_report_endpoint_truncates_user_agent():
    repository = FakeReportRepository()

    response = request(
        "POST",
        create_test_app(repository),
        "/recipe/report",
        headers={"User-Agent": "a" * 1100},
        json={
            "recipe_url": "https://example.com/recipe",
            "categories": ["metadata"],
            "recipe_snapshot": {"title": "Example"},
            "client_version": "test-client",
        },
    )

    assert response.status_code == 204
    assert repository.user_reports[0].user_agent == "a" * 1024


def test_report_endpoint_rejects_unknown_fields():
    response = request(
        "POST",
        create_test_app(FakeReportRepository()),
        "/recipe/report",
        json={
            "recipe_url": "https://example.com/recipe",
            "categories": ["metadata"],
            "recipe_snapshot": {"title": "Example"},
            "client_version": "test-client",
            "origin": "user",
        },
    )

    assert response.status_code == 422


def test_report_endpoint_rejects_unable_to_parse_from_clients():
    response = request(
        "POST",
        create_test_app(FakeReportRepository()),
        "/recipe/report",
        json={
            "recipe_url": "https://example.com/recipe",
            "categories": ["unable_to_parse"],
            "recipe_snapshot": {"title": "Example"},
            "client_version": "test-client",
        },
    )

    assert response.status_code == 422


def test_report_endpoint_rejects_duplicate_categories():
    response = request(
        "POST",
        create_test_app(FakeReportRepository()),
        "/recipe/report",
        json={
            "recipe_url": "https://example.com/recipe",
            "categories": ["metadata", "metadata"],
            "recipe_snapshot": {"title": "Example"},
            "client_version": "test-client",
        },
    )

    assert response.status_code == 422


def test_report_endpoint_rejects_empty_category_list():
    response = request(
        "POST",
        create_test_app(FakeReportRepository()),
        "/recipe/report",
        json={
            "recipe_url": "https://example.com/recipe",
            "categories": [],
            "recipe_snapshot": {"title": "Example"},
            "client_version": "test-client",
        },
    )

    assert response.status_code == 422


def test_report_endpoint_requires_note_for_other_category():
    response = request(
        "POST",
        create_test_app(FakeReportRepository()),
        "/recipe/report",
        json={
            "recipe_url": "https://example.com/recipe",
            "categories": ["other"],
            "note": "   ",
            "recipe_snapshot": {"title": "Example"},
            "client_version": "test-client",
        },
    )

    assert response.status_code == 422


def test_report_endpoint_requires_snapshot():
    response = request(
        "POST",
        create_test_app(FakeReportRepository()),
        "/recipe/report",
        json={
            "recipe_url": "https://example.com/recipe",
            "categories": ["metadata"],
            "client_version": "test-client",
        },
    )

    assert response.status_code == 422


def test_report_endpoint_requires_client_version():
    response = request(
        "POST",
        create_test_app(FakeReportRepository()),
        "/recipe/report",
        json={
            "recipe_url": "https://example.com/recipe",
            "categories": ["metadata"],
            "recipe_snapshot": {"title": "Example"},
        },
    )

    assert response.status_code == 422


def test_report_endpoint_rejects_oversized_url():
    response = request(
        "POST",
        create_test_app(FakeReportRepository()),
        "/recipe/report",
        json={
            "recipe_url": "https://example.com/" + "a" * 2049,
            "categories": ["metadata"],
            "recipe_snapshot": {"title": "Example"},
            "client_version": "test-client",
        },
    )

    assert response.status_code == 422


def test_report_endpoint_rejects_oversized_note():
    response = request(
        "POST",
        create_test_app(FakeReportRepository()),
        "/recipe/report",
        json={
            "recipe_url": "https://example.com/recipe",
            "categories": ["metadata"],
            "note": "a" * 4001,
            "recipe_snapshot": {"title": "Example"},
            "client_version": "test-client",
        },
    )

    assert response.status_code == 422


def test_report_endpoint_rejects_oversized_snapshot():
    response = request(
        "POST",
        create_test_app(FakeReportRepository()),
        "/recipe/report",
        json={
            "recipe_url": "https://example.com/recipe",
            "categories": ["metadata"],
            "recipe_snapshot": {"description": "a" * (128 * 1024)},
            "client_version": "test-client",
        },
    )

    assert response.status_code == 422


def test_report_endpoint_accepts_snapshot_at_compact_json_size_limit():
    repository = FakeReportRepository()
    snapshot = {"description": "a" * 131_054}

    assert len(
        json.dumps(snapshot, ensure_ascii=False, separators=(",", ":")).encode()
    ) == 131_072

    response = request(
        "POST",
        create_test_app(repository),
        "/recipe/report",
        json={
            "recipe_url": "https://example.com/recipe",
            "categories": ["metadata"],
            "recipe_snapshot": snapshot,
            "client_version": "test-client",
        },
    )

    assert response.status_code == 204
    assert repository.user_reports[0].recipe_snapshot == snapshot


def test_report_endpoint_rejects_oversized_client_version():
    response = request(
        "POST",
        create_test_app(FakeReportRepository()),
        "/recipe/report",
        json={
            "recipe_url": "https://example.com/recipe",
            "categories": ["metadata"],
            "recipe_snapshot": {"title": "Example"},
            "client_version": "a" * 129,
        },
    )

    assert response.status_code == 422


def test_report_endpoint_rejects_body_above_limit():
    response = request(
        "POST",
        create_test_app(FakeReportRepository()),
        "/recipe/report",
        json={
            "recipe_url": "https://example.com/recipe",
            "categories": ["metadata"],
            "recipe_snapshot": {"description": "a" * (144 * 1024)},
            "client_version": "test-client",
        },
    )

    assert response.status_code == 413


def test_report_endpoint_returns_503_when_repository_fails():
    response = request(
        "POST",
        create_test_app(FailingReportRepository()),
        "/recipe/report",
        json={
            "recipe_url": "https://example.com/recipe",
            "categories": ["metadata"],
            "recipe_snapshot": {"title": "Example"},
            "client_version": "test-client",
        },
    )

    assert response.status_code == 503


def test_recipe_endpoint_records_automatic_parse_failure(monkeypatch):
    monkeypatch.setattr(routes, "recipe_scraper", EmptyRecipeScraper())
    repository = FakeReportRepository()

    response = request(
        "GET",
        create_test_app(repository),
        "/recipe?url=https://example.com/page",
        headers={"User-Agent": "chorba-test"},
    )

    assert response.status_code == 422
    assert repository.parse_failures == [
        {
            "recipe_url": "https://example.com/page",
            "api_version": "test-api",
            "user_agent": "chorba-test",
        }
    ]


@pytest.mark.anyio
async def test_recipe_endpoint_defers_parse_failure_report_until_background(
    monkeypatch,
):
    monkeypatch.setattr(routes, "recipe_scraper", EmptyRecipeScraper())
    repository = FakeReportRepository()
    app = create_test_app(repository)

    async with app.router.lifespan_context(app):
        request = Request(
            {
                "type": "http",
                "app": app,
                "headers": [(b"user-agent", b"chorba-test")],
            }
        )
        response = await routes.get_recipe(
            url="https://example.com/page", request=request
        )

        assert response.status_code == 422
        assert json.loads(response.body) == {
            "detail": "Could not parse recipe from URL"
        }
        assert repository.parse_failures == []

        await response.background()

    assert repository.parse_failures == [
        {
            "recipe_url": "https://example.com/page",
            "api_version": "test-api",
            "user_agent": "chorba-test",
        }
    ]


def test_recipe_endpoint_preserves_422_when_automatic_report_fails(monkeypatch):
    monkeypatch.setattr(routes, "recipe_scraper", EmptyRecipeScraper())

    response = request(
        "GET",
        create_test_app(FailingReportRepository()),
        "/recipe?url=https://example.com/page"
    )

    assert response.status_code == 422
    assert response.json() == {"detail": "Could not parse recipe from URL"}


def test_recipe_endpoint_preserves_422_when_automatic_report_fails_unexpectedly(
    monkeypatch, caplog
):
    monkeypatch.setattr(routes, "recipe_scraper", EmptyRecipeScraper())

    with caplog.at_level(logging.ERROR, logger=routes.__name__):
        response = request(
            "GET",
            create_test_app(UnexpectedFailingReportRepository()),
            "/recipe?url=https://example.com/page",
        )

    assert response.status_code == 422
    assert response.json() == {"detail": "Could not parse recipe from URL"}
    assert "Failed to save automatic recipe parse failure report" in caplog.messages


def test_recipe_endpoint_does_not_report_source_404(monkeypatch):
    monkeypatch.setattr(routes, "recipe_scraper", NotFoundRecipeScraper())
    repository = FakeReportRepository()

    response = request(
        "GET",
        create_test_app(repository),
        "/recipe?url=https://example.com/missing"
    )

    assert response.status_code == 404
    assert repository.parse_failures == []
