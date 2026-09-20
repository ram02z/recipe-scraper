from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI

from chorba.config import Settings
from chorba.lib.markup._schema_org import (
    configure_ingredient_parser_nltk_data,
    ensure_ingredient_parser_ready,
)
from chorba.web.body_limit import BodyLimitMiddleware
from chorba.web.reports import (
    PostgresRecipeReportRepository,
    RecipeReportRepository,
    create_recipe_report_pool,
)
from chorba.web.routes import router

class _DefaultRepository:
    pass


_DEFAULT_REPOSITORY = _DefaultRepository()


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_ingredient_parser_nltk_data()
    ensure_ingredient_parser_ready()
    settings = getattr(app.state, "settings_override", None) or Settings.from_env()
    app.state.settings = settings

    repository_override = getattr(app.state, "recipe_report_repository_override", _DEFAULT_REPOSITORY)
    pool = None
    if repository_override is _DEFAULT_REPOSITORY:
        pool = create_recipe_report_pool(settings.database_url)
        await pool.open()
        app.state.recipe_report_pool = pool
        app.state.recipe_report_repository = PostgresRecipeReportRepository(pool)
    else:
        app.state.recipe_report_repository = repository_override

    try:
        yield
    finally:
        if pool is not None:
            await pool.close()


def create_app(
    *,
    settings: Settings | None = None,
    report_repository: RecipeReportRepository | None | _DefaultRepository = _DEFAULT_REPOSITORY,
) -> FastAPI:
    app = FastAPI(title="Chorba API", lifespan=lifespan)
    if settings is not None:
        app.state.settings_override = settings
    if report_repository is not _DEFAULT_REPOSITORY:
        app.state.recipe_report_repository_override = report_repository

    app.add_middleware(BodyLimitMiddleware)
    app.include_router(router)

    return app


app = create_app()


def main():
    uvicorn.run("chorba.cmd.server:app", host="0.0.0.0", port=8000, reload=True)


if __name__ == "__main__":
    main()
