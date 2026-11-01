"""Offline tests for the Learn-panel content endpoint (app.content_api).

GET /api/content serves static card JSON with no model calls, so these
tests call ``load_content`` / ``get_content`` directly instead of going
through TestClient. They also pin the content contracts the frontend
relies on: card shapes, unique ids, fallback images present on disk,
and every fallacy ``taxonomy_name`` matching a FallacyHunter output
name exactly (badge click opens the card on that match).
"""

import re
from pathlib import Path

from app.content_api import (
    FALLACIES_PATH,
    PHILOSOPHERS_PATH,
    ContentBundle,
    get_content,
    load_content,
)
from app.fallacy import load_fallacy_prompt

REPO = Path(__file__).resolve().parents[2]
FRONTEND_PUBLIC = REPO / "frontend" / "public"
HEX_COLOR = re.compile(r"^#[0-9a-fA-F]{6}$")


def test_load_content_returns_all_cards():
    bundle = load_content()
    assert isinstance(bundle, ContentBundle)
    assert len(bundle.philosophers) == 6
    assert len(bundle.fallacies) == 20
    assert PHILOSOPHERS_PATH.is_file()
    assert FALLACIES_PATH.is_file()


def test_card_ids_unique_and_fields_filled():
    bundle = load_content()
    phil_ids = [card.id for card in bundle.philosophers]
    assert len(set(phil_ids)) == len(phil_ids)
    fal_ids = [card.id for card in bundle.fallacies]
    assert len(set(fal_ids)) == len(fal_ids)
    for card in bundle.philosophers:
        assert card.name.strip()
        assert card.tagline.strip()
        assert card.summary.strip()
        assert card.method
        assert len(card.colors) == 2
        assert all(HEX_COLOR.match(color) for color in card.colors)
        assert card.image_prompt.strip()
    for card in bundle.fallacies:
        assert card.name.strip()
        assert card.what.strip()
        assert card.example.strip()
        assert card.tip.strip()
        assert len(card.colors) == 2
        assert all(HEX_COLOR.match(color) for color in card.colors)
        assert card.image_prompt.strip()


def test_judge_flags_match_philosopher_panel():
    bundle = load_content()
    judges = {card.id for card in bundle.philosophers if card.judge}
    assert judges == {
        "socrates",
        "aristotle",
        "hypatia",
        "kant",
        "marcus-aurelius",
        "epicurus",
    }
    # Every judge card points at its method, not a placeholder.
    for card in bundle.philosophers:
        assert "coming soon" not in card.in_hypatia.lower()


def test_fallback_images_exist_on_disk():
    bundle = load_content()
    for card in [*bundle.philosophers, *bundle.fallacies]:
        path = FRONTEND_PUBLIC / card.fallback_image.lstrip("/")
        assert path.is_file(), f"missing fallback image: {card.fallback_image}"
        assert card.image.startswith("/illustrations/")
        assert card.fallback_image.startswith("/illustrations/")
        # Primary images are lightweight WebP, not multi-megabyte PNGs.
        assert card.image.endswith(".webp"), card.image
        image_path = FRONTEND_PUBLIC / card.image.lstrip("/")
        assert image_path.is_file(), f"missing image: {card.image}"
        assert image_path.stat().st_size < 500_000, card.image


def test_taxonomy_names_match_hunter_output_names():
    """Badge click matches on taxonomy_name == fallacy name, so every
    taxonomy_name must be one of the exact output names in fallacy.md."""
    bundle = load_content()
    prompt = load_fallacy_prompt()
    names = [card.taxonomy_name for card in bundle.fallacies]
    assert len(set(names)) == len(names)
    for name in names:
        assert f'"{name}"' in prompt, f"{name} is not an exact Hunter output name"


def test_get_content_returns_bundle():
    bundle = get_content()
    assert isinstance(bundle, ContentBundle)
    assert len(bundle.philosophers) == 6
    assert len(bundle.fallacies) == 20
