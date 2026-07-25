from curl_cffi import requests
from fastapi import APIRouter, HTTPException

from chorba.web.models import RecipeResponse
from chorba.lib.markup.scraper import RecipeScraper

router = APIRouter()

recipe_scraper = RecipeScraper()


@router.get("/recipe", response_model=RecipeResponse)
async def get_recipe(url: str):
    try:
        recipe = recipe_scraper.scrape_from_url(url)
    except requests.RequestsError as error:
        status_code = getattr(error.response, "status_code", None)
        if status_code == 404:
            raise HTTPException(status_code=404, detail="Recipe URL not found") from error
        raise

    if recipe is None:
        raise HTTPException(status_code=422, detail="Could not parse recipe from URL")

    return RecipeResponse(recipe=recipe)
