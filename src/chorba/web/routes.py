from fastapi import APIRouter

from chorba.web.models import RecipeResponse
from chorba.lib.markup.scraper import RecipeScraper

router = APIRouter()

recipe_scraper = RecipeScraper()


@router.get("/recipe", response_model=RecipeResponse)
async def get_recipe(url: str):
    recipe = recipe_scraper.scrape_from_url(url)

    return RecipeResponse(recipe=recipe)
