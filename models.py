from dataclasses import dataclass


@dataclass
class Ingredient:
    name: str


@dataclass
class Recipe:
    title: str
    ingredients: list[Ingredient]
    directions: list[str]
