"""One-off Learn-card illustration generator (TASKS.md task 26).

Reads every `image_prompt` from `backend/app/content/philosophers.json`
and `backend/app/content/fallacies.json`, requests one square WebP per
card from Muse Image through the Meta Model API, and saves it to the
card's `image` path under `frontend/public/`. WebP keeps each card at
tens of kilobytes instead of megabytes of PNG. Files that already exist
are skipped, so re-running is cheap and safe.

Not run by check.ps1. Run once from the repo root:

    py scripts/generate_images.py

Cost: 26 cards x $0.01 per image = ~$0.26 (only successfully returned
images are billed). Use `--limit 1` first for a $0.01 smoke test.

Needs `META_API_KEY` and `META_IMAGE_MODEL` in `backend/.env`
(see `backend/.env.example`). Stdlib only.
"""

from __future__ import annotations

import argparse
import base64
import binascii
import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import NoReturn

ROOT = Path(__file__).resolve().parents[1]
DOTENV = ROOT / "backend" / ".env"
PHILOSOPHERS_JSON = ROOT / "backend" / "app" / "content" / "philosophers.json"
FALLACIES_JSON = ROOT / "backend" / "app" / "content" / "fallacies.json"
PUBLIC_DIR = ROOT / "frontend" / "public"

DEFAULT_BASE_URL = "https://api.meta.ai/v1"
SLEEP_SECONDS = 2.0
RETRY_WAIT_SECONDS = 15.0
REQUEST_TIMEOUT_SECONDS = 180
PRICE_PER_IMAGE_USD = 0.01


def load_dotenv(path: Path) -> dict[str, str]:
    """Parse KEY=VALUE lines; existing process env wins (no dependency)."""
    values: dict[str, str] = {}
    if not path.is_file():
        return values
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip("'\"")
        if key and key not in os.environ:
            values[key] = value
    return values


def fail(message: str) -> NoReturn:
    print(f"ERROR: {message}", file=sys.stderr)
    raise SystemExit(1)


def collect_cards() -> list[tuple[str, str, str]]:
    """Return (card id, image_prompt, image path) for every card."""
    cards: list[tuple[str, str, str]] = []
    for path, key in ((PHILOSOPHERS_JSON, "philosophers"), (FALLACIES_JSON, "fallacies")):
        if not path.is_file():
            fail(f"missing content file: {path}")
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            fail(f"{path.name} is not valid JSON: {exc}")
        for item in data[key]:
            cards.append((item["id"], item["image_prompt"], item["image"]))
    return cards


def request_webp(endpoint: str, api_key: str, model: str, prompt: str) -> bytes:
    """POST one square image request; return decoded WebP bytes (429 retried once)."""
    body = json.dumps(
        {
            "model": model,
            "prompt": prompt,
            "n": 1,
            "size": "1024x1024",
            "response_format": "b64_json",
            "output_format": "webp",
        }
    ).encode("utf-8")
    last_error = ""
    for attempt in (1, 2):
        request = urllib.request.Request(
            endpoint,
            data=body,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            try:
                detail = exc.read().decode("utf-8", "replace")[:300]
            except Exception:
                detail = ""
            last_error = f"HTTP {exc.code}: {detail}"
            if exc.code == 429 and attempt == 1:
                print(f"  rate limited, waiting {RETRY_WAIT_SECONDS:.0f}s and retrying…")
                time.sleep(RETRY_WAIT_SECONDS)
                continue
            fail(last_error)
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            fail(f"request failed: {exc}")
        try:
            raw = payload["data"][0]["b64_json"]
            image_bytes = base64.b64decode(raw)
        except (KeyError, IndexError, TypeError, binascii.Error) as exc:
            fail(f"unexpected image response shape: {exc}")
        if not (image_bytes.startswith(b"RIFF") and image_bytes[8:12] == b"WEBP"):
            fail("response bytes are not a WebP image")
        return image_bytes
    fail(last_error or "request failed")


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate Learn-card illustrations with Muse Image.")
    parser.add_argument("--limit", type=int, default=0, help="only generate the first N cards (0 = all)")
    parser.add_argument("--force", action="store_true", help="regenerate even when the image exists")
    parser.add_argument("--dry-run", action="store_true", help="list cards without calling the API")
    args = parser.parse_args()

    cards = collect_cards()
    if args.limit > 0:
        cards = cards[: args.limit]
    if args.dry_run:
        print(f"{len(cards)} cards (dry run, no API calls):")
        for card_id, _, image in cards:
            exists = (PUBLIC_DIR / image.lstrip("/")).is_file()
            print(f"  {'skip (exists)' if exists else 'would generate'}: {card_id} -> {image}")
        return

    env = load_dotenv(DOTENV)
    base_url = os.environ.get("META_BASE_URL", env.get("META_BASE_URL", DEFAULT_BASE_URL)).rstrip("/")
    api_key = os.environ.get("META_API_KEY", env.get("META_API_KEY", ""))
    model = os.environ.get("META_IMAGE_MODEL", env.get("META_IMAGE_MODEL", ""))
    if not api_key:
        fail("META_API_KEY is not set. Add it to backend/.env (see backend/.env.example).")
    if not model:
        fail("META_IMAGE_MODEL is not set. Add META_IMAGE_MODEL=muse-image-1.0 to backend/.env.")
    print(f"{len(cards)} cards, model {model}, saving under frontend/public/")

    endpoint = f"{base_url}/images/generations"
    generated = 0
    skipped = 0
    for index, (card_id, prompt, image) in enumerate(cards):
        target = PUBLIC_DIR / image.lstrip("/")
        if target.is_file() and not args.force:
            print(f"[{index + 1}/{len(cards)}] skip (exists): {card_id}")
            skipped += 1
            continue
        print(f"[{index + 1}/{len(cards)}] generating: {card_id} …")
        webp = request_webp(endpoint, api_key, model, prompt)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(webp)
        print(f"  saved {target.relative_to(ROOT)} ({len(webp)} bytes)")
        generated += 1
        if index < len(cards) - 1:
            time.sleep(SLEEP_SECONDS)
    print(f"Done: {generated} generated, {skipped} skipped.")
    print(f"Estimated spend this run: ${generated * PRICE_PER_IMAGE_USD:.2f}")


if __name__ == "__main__":
    main()
