"""Demo mode (TASKS.md task 19).

GET /api/demo loads the last saved analysis from
``backend/data/last_result.json`` instantly, with no model calls, so the
demo video can be recorded without waiting on the pipeline. The file is
written by POST /api/analyze (``app.analyze.save_result``).
"""

from __future__ import annotations

import json
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import ValidationError

from app.schemas import DebateResult

router = APIRouter()

LAST_RESULT_PATH = Path(__file__).resolve().parents[1] / "data" / "last_result.json"

MISSING_MESSAGE = (
    "No saved demo result yet. "
    "Run POST /api/analyze once to create backend/data/last_result.json."
)


def load_demo_result(path: Path | None = None) -> DebateResult:
    """Read and validate the saved demo result.

    Raises FileNotFoundError when the file does not exist and ValueError
    when it is not valid contract JSON.
    """
    actual = LAST_RESULT_PATH if path is None else path
    try:
        raw = actual.read_text(encoding="utf-8")
    except FileNotFoundError:
        raise
    except OSError as exc:
        raise ValueError(f"Could not read saved demo result: {exc}") from exc
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Saved demo result is not valid JSON: {exc}") from exc
    try:
        return DebateResult.model_validate(data)
    except ValidationError as exc:
        raise ValueError(f"Saved demo result is not a valid analysis: {exc}") from exc


@router.get("/api/demo", response_model=DebateResult)
def get_demo() -> DebateResult:
    """Return the saved analysis instantly (no model calls)."""
    try:
        return load_demo_result()
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=MISSING_MESSAGE)
    except ValueError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
