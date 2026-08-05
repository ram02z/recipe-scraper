import traceback

import pytest
from fastapi.testclient import TestClient
from psycopg_pool import PoolClosed

from chorba.cmd.server import create_app
from chorba.config import Settings
from chorba.web.body_limit import BodyLimitMiddleware
from chorba.web.reports import (
    PostgresRecipeReportRepository,
    RecipeReportUnavailable,
    create_recipe_report_pool,
)


def test_create_recipe_report_pool_passes_structured_connection_parameters(monkeypatch):
    pool_calls = []
    expected_pool = object()

    def create_pool(conninfo, **kwargs):
        pool_calls.append((conninfo, kwargs))
        return expected_pool

    monkeypatch.setattr("chorba.web.reports.AsyncConnectionPool", create_pool)

    pool = create_recipe_report_pool(
        "postgresql://reporter:p%40ss%25word@db.example.com:5432/chorba"
        "?sslmode=require"
    )

    assert pool is expected_pool
    assert pool_calls == [
        (
            "",
            {
                "kwargs": {
                    "user": "reporter",
                    "password": "p@ss%word",
                    "dbname": "chorba",
                    "host": "db.example.com",
                    "port": "5432",
                    "sslmode": "require",
                },
                "open": False,
                "min_size": 0,
                "max_size": 5,
                "timeout": 5,
            },
        )
    ]


def test_create_recipe_report_pool_hides_malformed_database_url_details():
    database_url = "postgresql://reporter:secret%s2@db.example.com:5432/chorba"

    with pytest.raises(ValueError) as exc_info:
        create_recipe_report_pool(database_url)

    rendered_error = "".join(
        traceback.format_exception(
            type(exc_info.value),
            exc_info.value,
            exc_info.value.__traceback__,
        )
    )
    assert str(exc_info.value) == "DATABASE_URL is invalid"
    assert exc_info.value.__context__ is None
    assert exc_info.value.__cause__ is None
    assert "secret%s2" not in rendered_error
    assert "invalid percent-encoded token" not in rendered_error


@pytest.mark.anyio
async def test_body_limit_rejects_malformed_content_length():
    async def app(scope, receive, send):
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"ok"})

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    sent = []

    async def send(message):
        sent.append(message)

    middleware = BodyLimitMiddleware(app)
    await middleware(
        {
            "type": "http",
            "headers": [(b"content-length", b"not-a-number")],
        },
        receive,
        send,
    )

    assert sent[0]["status"] == 400


class ClosedPool:
    def connection(self):
        raise PoolClosed("pool is closed")


@pytest.mark.anyio
async def test_repository_translates_pool_closed_errors():
    repository = PostgresRecipeReportRepository(ClosedPool())

    with pytest.raises(RecipeReportUnavailable):
        await repository.create_parse_failure(
            recipe_url="https://example.com/recipe",
            api_version="test-api",
            user_agent=None,
        )


class FakePool:
    def __init__(self):
        self.is_open = False
        self.is_closed = False

    async def open(self):
        self.is_open = True

    async def close(self):
        self.is_closed = True


class FakeRecipeReportRepository:
    async def create_user_report(self, report):
        pass

    async def create_parse_failure(
        self,
        recipe_url: str,
        api_version: str,
        user_agent: str | None,
    ) -> None:
        pass


SETTINGS = Settings(
    database_url="postgresql://test.example/chorba",
    api_version="test-api",
)


def test_app_lifespan_constructs_and_closes_default_report_repository(monkeypatch):
    pool = FakePool()
    database_urls = []

    def create_pool(database_url):
        database_urls.append(database_url)
        return pool

    monkeypatch.setattr("chorba.cmd.server.create_recipe_report_pool", create_pool)
    monkeypatch.setattr("chorba.cmd.server.ensure_ingredient_parser_ready", lambda: None)
    app = create_app(settings=SETTINGS)

    assert not hasattr(app.state, "settings")
    assert not hasattr(app.state, "recipe_report_repository")

    with TestClient(app):
        assert app.state.settings is SETTINGS
        assert pool.is_open
        assert isinstance(
            app.state.recipe_report_repository,
            PostgresRecipeReportRepository,
        )

    assert database_urls == ["postgresql://test.example/chorba"]
    assert pool.is_closed


def test_app_lifespan_uses_explicit_report_repository_without_pool(monkeypatch):
    def fail_if_pool_created(database_url):
        raise AssertionError(f"unexpected pool for {database_url}")

    monkeypatch.setattr(
        "chorba.cmd.server.create_recipe_report_pool",
        fail_if_pool_created,
    )
    monkeypatch.setattr("chorba.cmd.server.ensure_ingredient_parser_ready", lambda: None)
    repository = FakeRecipeReportRepository()
    app = create_app(settings=SETTINGS, report_repository=repository)

    assert not hasattr(app.state, "settings")
    assert not hasattr(app.state, "recipe_report_repository")

    with TestClient(app):
        assert app.state.settings is SETTINGS
        assert app.state.recipe_report_repository is repository


def test_app_lifespan_disables_reporting_with_explicit_none(monkeypatch):
    def fail_if_pool_created(database_url):
        raise AssertionError(f"unexpected pool for {database_url}")

    monkeypatch.setattr(
        "chorba.cmd.server.create_recipe_report_pool",
        fail_if_pool_created,
    )
    monkeypatch.setattr("chorba.cmd.server.ensure_ingredient_parser_ready", lambda: None)
    app = create_app(settings=SETTINGS, report_repository=None)

    assert not hasattr(app.state, "settings")
    assert not hasattr(app.state, "recipe_report_repository")

    with TestClient(app):
        assert app.state.settings is SETTINGS
        assert app.state.recipe_report_repository is None
