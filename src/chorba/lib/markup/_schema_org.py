from datetime import timedelta

from pydantic import Field, TypeAdapter, computed_field
from pydantic.dataclasses import dataclass


timedelta_adapter = TypeAdapter(timedelta)


def _parse_duration_ms(value: str | None) -> int | None:
    if not value:
        return None

    try:
        duration = timedelta_adapter.validate_python(value)
    except Exception:
        return None

    return int(duration.total_seconds() * 1000)


def _format_duration_ms(duration_ms: int | None) -> str | None:
    if duration_ms is None or duration_ms == 0:
        return None

    total_minutes = duration_ms // 60000
    hours, minutes = divmod(total_minutes, 60)

    if hours == 0:
        return f"{total_minutes} min"
    if minutes == 0:
        return f"{hours} hr"
    return f"{hours} hr {minutes} min"


@dataclass
class Ingredient:
    name: str


@dataclass
class Recipe:
    PROPERTY_FIELDS = [
        "name",
        "recipeIngredient",
        "recipeInstructions",
        "prepTime",
        "cookTime",
    ]
    _data: dict = Field(exclude=True)

    def __init__(self, data: dict) -> None:
        self._data = data

    @computed_field
    @property
    def title(self) -> str:
        return self._data.get("name", "")

    @computed_field
    @property
    def ingredients(self) -> list[Ingredient]:
        return [
            Ingredient(name=item) for item in self._data.get("recipeIngredient", [])
        ]

    @computed_field
    @property
    def directions(self) -> list[str]:
        recipeInstructions = self._data.get("recipeInstructions", [])
        directions = []

        if isinstance(recipeInstructions, str):
            directions.append(recipeInstructions.strip())
        elif isinstance(recipeInstructions, list):
            for item in recipeInstructions:
                if isinstance(item, str):
                    # String in array
                    directions.append(item.strip())
                elif isinstance(item, dict):
                    if item.get("@type") == "HowToStep":
                        text = item.get("text", "")
                        if text:
                            directions.append(text.strip())
                    elif item.get("@type") == "HowToSection":
                        # Handle section with multiple steps
                        section_name = item.get("name", "")
                        if section_name:
                            directions.append(f"{section_name}:")

                        section_steps = item.get("itemListElement", [])
                        for step in section_steps:
                            if (
                                isinstance(step, dict)
                                and step.get("@type") == "HowToStep"
                            ):
                                text = step.get("text", "")
                                if text:
                                    directions.append(f"  - {text.strip()}")
                            elif isinstance(step, str):
                                directions.append(f"  - {step.strip()}")

        return directions

    @property
    def _prep_time_ms(self) -> int | None:
        return _parse_duration_ms(self._data.get("prepTime"))

    @property
    def _cook_time_ms(self) -> int | None:
        return _parse_duration_ms(self._data.get("cookTime"))

    @computed_field
    @property
    def time(self) -> str | None:
        duration_ms = self._prep_time_ms or self._cook_time_ms

        if self._prep_time_ms and self._cook_time_ms:
            duration_ms = self._prep_time_ms + self._cook_time_ms

        return _format_duration_ms(duration_ms)
