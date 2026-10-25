"""Read-only built-ins plus operator-owned JSON recipes."""
import json
from importlib.resources import files
from pathlib import Path
from .models import Recipe


def built_in_recipes() -> dict[str, Recipe]:
    source = files("membrane_control").joinpath("resources/presets.json")
    return {d["name"]: Recipe.from_dict(d) for d in json.loads(source.read_text(encoding="utf-8"))}


def read_recipe(path) -> Recipe:
    path = Path(path)
    if path.stat().st_size > 65536:
        raise ValueError("Recipe file is too large")
    return Recipe.from_dict(json.loads(path.read_text(encoding="utf-8")))


def write_recipe(path, recipe: Recipe):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(recipe.to_dict(), indent=2, allow_nan=False, ensure_ascii=False) + "\n", encoding="utf-8")
    temporary.replace(path)
