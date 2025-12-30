from dataclasses import dataclass


@dataclass
class Ingredient:
    name: str


@dataclass
class Recipe:
    PROPERTY_FIELDS = ["name", "recipeIngredient", "recipeInstructions"]
    _data: dict

    def __init__(self, data: dict) -> None:
        self._data = data

    @property
    def title(self) -> str:
        return self._data.get("name", "")

    @property
    def ingredients(self) -> list[Ingredient]:
        return [
            Ingredient(name=item) for item in self._data.get("recipeIngredient", [])
        ]

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
