import logging

from curl_cffi import requests
from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import JSONResponse
from starlette.background import BackgroundTask

from chorba.lib.markup.scraper import RecipeScraper
from chorba.web.models import RecipeReportRequest, RecipeResponse
from chorba.web.reports import RecipeReportUnavailable, UserRecipeReport

logger = logging.getLogger(__name__)

router = APIRouter()

recipe_scraper = RecipeScraper()


def _truncate_user_agent(user_agent: str | None) -> str | None:
    if user_agent is None:
        return None
    return user_agent[:1024]


def _settings(request: Request):
    return request.app.state.settings


def _report_repository(request: Request):
    return getattr(request.app.state, "recipe_report_repository", None)


@router.post("/recipe/report", status_code=204, response_class=Response)
async def report_recipe(report_request: RecipeReportRequest, request: Request):
    repository = _report_repository(request)
    if repository is None:
        raise HTTPException(status_code=503, detail="Recipe reports are unavailable")

    report = UserRecipeReport(
        recipe_url=report_request.recipe_url,
        categories=[category.value for category in report_request.categories],
        note=report_request.note,
        recipe_snapshot=report_request.recipe_snapshot,
        client_version=report_request.client_version,
        api_version=_settings(request).api_version,
        user_agent=_truncate_user_agent(request.headers.get("user-agent")),
    )

    try:
        await repository.create_user_report(report)
    except RecipeReportUnavailable as error:
        raise HTTPException(status_code=503, detail="Could not save recipe report") from error

    return Response(status_code=204)


async def _report_parse_failure(request: Request, url: str) -> None:
    repository = _report_repository(request)
    if repository is None:
        return

    try:
        await repository.create_parse_failure(
            recipe_url=url,
            api_version=_settings(request).api_version,
            user_agent=_truncate_user_agent(request.headers.get("user-agent")),
        )
    except Exception:
        logger.exception("Failed to save automatic recipe parse failure report")


@router.get("/recipe", response_model=RecipeResponse)
async def get_recipe(url: str, request: Request):
    try:
        recipe = recipe_scraper.scrape_from_url(url)
    except requests.RequestsError as error:
        status_code = getattr(error.response, "status_code", None)
        if status_code == 404:
            raise HTTPException(status_code=404, detail="Recipe URL not found") from error
        raise

    if recipe is None:
        return JSONResponse(
            status_code=422,
            content={"detail": "Could not parse recipe from URL"},
            background=BackgroundTask(_report_parse_failure, request, url),
        )

    return RecipeResponse(recipe=recipe)
