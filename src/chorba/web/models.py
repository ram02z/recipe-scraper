from pydantic import BaseModel

from chorba.lib.markup._schema_org import Recipe


class RecipeResponse(BaseModel):
    recipe: Recipe
