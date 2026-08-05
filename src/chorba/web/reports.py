from dataclasses import dataclass
from typing import Any, Protocol

import psycopg
from psycopg.types.json import Jsonb
from psycopg_pool import AsyncConnectionPool, PoolTimeout


@dataclass(frozen=True)
class UserRecipeReport:
    recipe_url: str
    categories: list[str]
    note: str | None
    recipe_snapshot: dict[str, Any]
    client_version: str
    api_version: str
    user_agent: str | None


class RecipeReportUnavailable(Exception):
    pass


class RecipeReportRepository(Protocol):
    async def create_user_report(self, report: UserRecipeReport) -> None: ...

    async def create_parse_failure(
        self,
        recipe_url: str,
        api_version: str,
        user_agent: str | None,
    ) -> None: ...


class PostgresRecipeReportRepository:
    def __init__(self, pool: AsyncConnectionPool):
        self._pool = pool

    async def create_user_report(self, report: UserRecipeReport) -> None:
        await self._insert_report(
            origin="user",
            recipe_url=report.recipe_url,
            categories=report.categories,
            note=report.note,
            recipe_snapshot=report.recipe_snapshot,
            client_version=report.client_version,
            api_version=report.api_version,
            user_agent=report.user_agent,
        )

    async def create_parse_failure(
        self,
        recipe_url: str,
        api_version: str,
        user_agent: str | None,
    ) -> None:
        await self._insert_report(
            origin="automatic",
            recipe_url=recipe_url,
            categories=["unable_to_parse"],
            note=None,
            recipe_snapshot=None,
            client_version=None,
            api_version=api_version,
            user_agent=user_agent,
        )

    async def _insert_report(
        self,
        *,
        origin: str,
        recipe_url: str,
        categories: list[str],
        note: str | None,
        recipe_snapshot: dict[str, Any] | None,
        client_version: str | None,
        api_version: str,
        user_agent: str | None,
    ) -> None:
        try:
            async with self._pool.connection() as connection:
                await connection.execute(
                    """
                    insert into public.recipe_reports (
                        origin,
                        recipe_url,
                        categories,
                        note,
                        recipe_snapshot,
                        client_version,
                        api_version,
                        user_agent
                    ) values (%s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        origin,
                        recipe_url,
                        categories,
                        note,
                        Jsonb(recipe_snapshot) if recipe_snapshot is not None else None,
                        client_version,
                        api_version,
                        user_agent,
                    ),
                )
        except (psycopg.Error, PoolTimeout, TimeoutError) as error:
            raise RecipeReportUnavailable from error


def create_recipe_report_pool(database_url: str) -> AsyncConnectionPool:
    return AsyncConnectionPool(
        database_url,
        open=False,
        min_size=0,
        max_size=5,
        timeout=5,
    )
