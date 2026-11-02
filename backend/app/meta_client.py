"""Thin wrapper around the Meta Model API (chat + transcription).

All network calls in the backend go through this module, so pipeline code
never touches the network directly and tests can mock this module instead.

Verified shapes are in NOTES.md under "Verified API facts":
- Chat uses the OpenAI SDK pointed at ``META_BASE_URL`` with ``META_API_KEY``.
  Model IDs come from env vars only (``META_TEXT_MODEL`` / ``META_TRANSCRIBE_MODEL``)
  and are read lazily, so importing this module needs neither env vars nor network.
- Structured output uses ``response_format={"type": "json_schema", "json_schema":
  {"name": ..., "schema": {...}}}``. Replies are validated with pydantic and the
  call is retried once when the reply is not valid for the schema.
- Transcription is NOT an OpenAI SDK call: ``POST {META_BASE_URL}/asr/transcribe``
  via httpx, multipart with a ``request`` JSON part and an ``audio`` WAV part.
  The reply carries integer-millisecond times (divide by 1000 for seconds) and
  single-request speaker labels; mapping turns to segments is the caller's job.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Annotated, Any, TypeVar

import httpx
from dotenv import load_dotenv
from httpx import HTTPError
from openai import OpenAI, OpenAIError
from pydantic import BaseModel, BeforeValidator, ValidationError

# Secrets live only in backend/.env (gitignored). Load it explicitly so the
# backend works however it is started (with or without `uvicorn --env-file`).
# A missing file is fine: env vars may also come from the real environment.
load_dotenv(Path(__file__).resolve().parents[1] / ".env")

T = TypeVar("T", bound=BaseModel)

__all__ = [
    "MetaClientError",
    "TranscriptionTurn",
    "TranscriptionResult",
    "chat_json",
    "chat_json_validated",
    "transcribe_wav",
]

_TRANSCRIBE_PATH = "/asr/transcribe"
_TRANSCRIBE_AUDIO_ENCODING = "WAV"
# DIARIZATION is the only mode that attributes speech to speakers, which the
# argument map requires; it is also the model's full-accuracy batch mode.
# There is no faster/cheaper transcribe model to select: the single model is
# read from META_TRANSCRIBE_MODEL, and callers feed it the engine-native
# 24 kHz mono PCM WAV (see transcribe.py / wavEncode.ts) so the server does
# not resample. `languageBias`/`keywords` are deliberately left unset: with
# no hint the model auto-detects language (incl. code-switching), which is
# the correct default for an unknown debate.
_TRANSCRIBE_MODE = "DIARIZATION"
_MAX_ATTEMPTS = 2  # one initial try + one retry


class MetaClientError(RuntimeError):
    """Config, transport, or model-reply failure from the Meta Model API."""


class _InvalidReply(ValueError):
    """One chat reply was unusable (not JSON, or not a JSON object)."""


def _optional_speaker(value: Any) -> str | None:
    """Normalize a turn speaker: missing/blank means unattributed."""
    if value is None:
        return None
    text = str(value).strip()
    return text or None


class TranscriptionTurn(BaseModel):
    """One diarized turn; times are integer milliseconds."""

    # The live API returns integer turn ids (0, 1, 2, ...); coerce to str.
    turnId: Annotated[str, BeforeValidator(lambda value: str(value))]
    startMs: int
    endMs: int
    transcript: str = ""
    # DIARIZATION usually attributes every turn, but the live API can omit
    # `speaker` on turns it never attributed (its text/plain rendering calls
    # those `unknown:`) and can emit empty filler turns. Neither may fail
    # validation: the caller drops empty turns and lets an unattributed turn
    # inherit the neighbouring speaker.
    speaker: Annotated[str | None, BeforeValidator(_optional_speaker)] = None


class TranscriptionResult(BaseModel):
    """Validated ``POST .../asr/transcribe`` reply."""

    sessionId: str
    transcript: str
    audioDurationMs: int
    turns: list[TranscriptionTurn]


def _env(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise MetaClientError(
            f"{name} is not set; copy backend/.env.example to backend/.env and fill it in"
        )
    return value


def _chat_client() -> OpenAI:
    return OpenAI(base_url=_env("META_BASE_URL"), api_key=_env("META_API_KEY"))


def _request_chat_json(
    client: OpenAI,
    *,
    model_id: str,
    messages: list[dict[str, Any]],
    response_format: dict[str, Any],
) -> dict[str, Any]:
    """Single structured-output chat attempt; raises _InvalidReply on a bad reply."""
    try:
        completion = client.chat.completions.create(
            model=model_id,
            messages=messages,
            response_format=response_format,
        )
    except OpenAIError as exc:
        raise MetaClientError(f"chat request failed: {exc}") from exc
    try:
        content = completion.choices[0].message.content
        parsed = json.loads(content) if content and content.strip() else None
    except (AttributeError, IndexError, TypeError, json.JSONDecodeError) as exc:
        raise _InvalidReply(f"chat reply was not valid JSON: {exc}") from exc
    if not isinstance(parsed, dict):
        raise _InvalidReply("chat reply was not a JSON object")
    return parsed


def chat_json(
    messages: list[dict[str, Any]],
    *,
    json_schema: dict[str, Any],
    schema_name: str,
    model: str | None = None,
    client: OpenAI | None = None,
) -> dict[str, Any]:
    """Chat call with structured output; retried once when the reply is not valid JSON.

    ``model`` defaults to ``META_TEXT_MODEL``. Pass ``client`` only in tests.
    """
    model_id = model or _env("META_TEXT_MODEL")
    active = client if client is not None else _chat_client()
    response_format = {
        "type": "json_schema",
        "json_schema": {"name": schema_name, "schema": json_schema},
    }
    last_error: _InvalidReply | None = None
    for _ in range(_MAX_ATTEMPTS):
        try:
            return _request_chat_json(
                active,
                model_id=model_id,
                messages=messages,
                response_format=response_format,
            )
        except _InvalidReply as exc:
            last_error = exc
    raise MetaClientError(f"chat model returned invalid JSON twice: {last_error}")


def chat_json_validated(
    messages: list[dict[str, Any]],
    *,
    response_model: type[T],
    schema_name: str | None = None,
    model: str | None = None,
    client: OpenAI | None = None,
) -> T:
    """Chat call whose reply must validate as ``response_model``; retried once on failure.

    The JSON schema is derived from ``response_model`` so the schema sent and the
    validation applied can never drift apart. Pass ``client`` only in tests.
    """
    model_id = model or _env("META_TEXT_MODEL")
    active = client if client is not None else _chat_client()
    name = schema_name or response_model.__name__
    response_format = {
        "type": "json_schema",
        "json_schema": {"name": name, "schema": response_model.model_json_schema()},
    }
    last_error: Exception | None = None
    for _ in range(_MAX_ATTEMPTS):
        try:
            parsed = _request_chat_json(
                active,
                model_id=model_id,
                messages=messages,
                response_format=response_format,
            )
        except _InvalidReply as exc:
            last_error = exc
            continue
        try:
            return response_model.model_validate(parsed)
        except ValidationError as exc:
            last_error = exc
    raise MetaClientError(
        f"chat model reply failed {response_model.__name__} validation twice: {last_error}"
    )


def transcribe_wav(
    audio_wav: bytes,
    *,
    filename: str = "audio.wav",
    model: str | None = None,
    timeout_s: float = 300.0,
) -> TranscriptionResult:
    """Transcribe mono 16-bit PCM WAV audio (max 10 min, 32 MB) via httpx.

    ``model`` defaults to ``META_TRANSCRIBE_MODEL``. Raises MetaClientError on
    transport failures (including 400/413/429) and on unexpected reply shapes.
    """
    base_url = _env("META_BASE_URL").rstrip("/")
    api_key = _env("META_API_KEY")
    model_id = model or _env("META_TRANSCRIBE_MODEL")
    request_part = json.dumps(
        {
            "model": model_id,
            "audioEncoding": _TRANSCRIBE_AUDIO_ENCODING,
            "mode": _TRANSCRIBE_MODE,
        }
    )
    try:
        response = httpx.post(
            f"{base_url}{_TRANSCRIBE_PATH}",
            headers={"Authorization": f"Bearer {api_key}"},
            files={
                "request": (None, request_part, "application/json"),
                "audio": (filename, audio_wav, "audio/wav"),
            },
            timeout=timeout_s,
        )
        response.raise_for_status()
    except HTTPError as exc:
        raise MetaClientError(f"transcription request failed: {exc}") from exc
    try:
        return TranscriptionResult.model_validate(response.json())
    except (ValueError, ValidationError) as exc:
        raise MetaClientError(f"transcription reply failed validation: {exc}") from exc
