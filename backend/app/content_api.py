"""Learn-panel content (TASKS.md task 25).

GET /api/content serves the static card data for the Learn panel:
philosopher cards from ``app/content/philosophers.json`` and fallacy
cards from ``app/content/fallacies.json``. No model calls are made.
Each fallacy card's ``taxonomy_name`` matches a FallacyHunter output
``name`` exactly, so the frontend can open a card when its badge is
clicked on the map.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import TypeVar

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ValidationError

CardT = TypeVar("CardT", bound=BaseModel)

router = APIRouter()

CONTENT_DIR = Path(__file__).resolve().parent / "content"
PHILOSOPHERS_PATH = CONTENT_DIR / "philosophers.json"
FALLACIES_PATH = CONTENT_DIR / "fallacies.json"


class PhilosopherCard(BaseModel):
    """One philosopher card as stored in ``philosophers.json``."""

    id: str
    name: str
    years: str
    role: str
    judge: bool
    emoji: str
    colors: list[str]
    tagline: str
    summary: str
    method: list[str]
    in_hypatia: str
    image_prompt: str
    image: str
    fallback_image: str


class FallacyCard(BaseModel):
    """One fallacy card as stored in ``fallacies.json``."""

    id: str
    name: str
    emoji: str
    colors: list[str]
    what: str
    example: str
    tip: str
    image_prompt: str
    taxonomy_name: str
    image: str
    fallback_image: str


class ContentBundle(BaseModel):
    """Everything the Learn panel needs in one response."""

    philosophers: list[PhilosopherCard]
    fallacies: list[FallacyCard]


def _load_cards(path: Path, key: str, model: type[CardT]) -> list[CardT]:
    try:
        raw = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        raise
    except OSError as exc:
        raise ValueError(f"Could not read {path.name}: {exc}") from exc
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"{path.name} is not valid JSON: {exc}") from exc
    try:
        return [model.model_validate(item) for item in data[key]]
    except (KeyError, TypeError, ValidationError) as exc:
        raise ValueError(f"{path.name} has invalid card data: {exc}") from exc


def load_content() -> ContentBundle:
    """Read and validate both card files.

    Raises FileNotFoundError when a file is missing and ValueError
    when a file is not valid card JSON.
    """
    philosophers = _load_cards(PHILOSOPHERS_PATH, "philosophers", PhilosopherCard)
    fallacies = _load_cards(FALLACIES_PATH, "fallacies", FallacyCard)
    return ContentBundle(philosophers=philosophers, fallacies=fallacies)


@router.get("/api/content", response_model=ContentBundle)
def get_content() -> ContentBundle:
    """Return the Learn-panel cards (static, no model calls)."""
    try:
        return load_content()
    except FileNotFoundError as exc:
        raise HTTPException(status_code=500, detail=f"Learn content missing: {exc}") from exc
    except ValueError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
