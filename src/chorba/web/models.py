import json
from enum import StrEnum
from typing import Any
from urllib.parse import urlparse

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from chorba.lib.markup._schema_org import Recipe


class RecipeResponse(BaseModel):
    recipe: Recipe


class HealthResponse(BaseModel):
    status: str
    api_version: str


class UserReportCategory(StrEnum):
    INGREDIENT_PARSING = "ingredient_parsing"
    DIRECTIONS = "directions"
    MEDIA = "media"
    METADATA = "metadata"
    RENDERING = "rendering"
    OTHER = "other"


class RecipeReportRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    recipe_url: str = Field(
        description="HTTP or HTTPS URL, limited to 2048 bytes when UTF-8 encoded."
    )
    categories: list[UserReportCategory] = Field(
        min_length=1,
        max_length=6,
        json_schema_extra={"uniqueItems": True},
    )
    note: str | None = Field(
        default=None,
        max_length=4000,
        description=(
            "Optional note; trimmed of surrounding whitespace, with blank values "
            "normalized to null; required when categories includes 'other'."
        ),
    )
    recipe_snapshot: dict[str, Any] = Field(
        description=(
            "JSON object whose compact UTF-8 serialization is at most 128 KiB."
        )
    )
    client_version: str = Field(
        min_length=1,
        max_length=128,
        description=(
            "Client version; trimmed of surrounding whitespace and must be nonblank."
        ),
    )

    @field_validator("recipe_url")
    @classmethod
    def validate_recipe_url(cls, recipe_url: str) -> str:
        if len(recipe_url.encode()) > 2048:
            raise ValueError("recipe_url must be at most 2048 bytes")

        parsed = urlparse(recipe_url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("recipe_url must be an HTTP or HTTPS URL")

        return recipe_url

    @field_validator("categories")
    @classmethod
    def validate_unique_categories(
        cls, categories: list[UserReportCategory]
    ) -> list[UserReportCategory]:
        if len(set(categories)) != len(categories):
            raise ValueError("categories must be unique")
        return categories

    @field_validator("note")
    @classmethod
    def normalize_note(cls, note: str | None) -> str | None:
        if note is None:
            return None
        note = note.strip()
        return note or None

    @field_validator("recipe_snapshot")
    @classmethod
    def validate_snapshot_size(cls, recipe_snapshot: dict[str, Any]) -> dict[str, Any]:
        serialized = json.dumps(
            recipe_snapshot,
            ensure_ascii=False,
            separators=(",", ":"),
        )
        if len(serialized.encode()) > 128 * 1024:
            raise ValueError("recipe_snapshot must be at most 128 KiB")
        return recipe_snapshot

    @field_validator("client_version")
    @classmethod
    def validate_client_version(cls, client_version: str) -> str:
        client_version = client_version.strip()
        if not client_version:
            raise ValueError("client_version must not be blank")
        return client_version

    @model_validator(mode="after")
    def require_note_for_other(self) -> "RecipeReportRequest":
        if UserReportCategory.OTHER in self.categories and self.note is None:
            raise ValueError("note is required when category is other")
        return self
