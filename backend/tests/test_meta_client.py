"""Offline tests for app.meta_client: the OpenAI SDK client and httpx are faked."""

import json
from types import SimpleNamespace
from typing import Any

import httpx
import pytest
from pydantic import BaseModel

from app import meta_client
from app.meta_client import (
    MetaClientError,
    TranscriptionResult,
    chat_json,
    chat_json_validated,
    transcribe_wav,
)


@pytest.fixture
def env(monkeypatch):
    monkeypatch.setenv("META_BASE_URL", "https://api.meta.ai/v1")
    monkeypatch.setenv("META_API_KEY", "test-key")
    monkeypatch.setenv("META_TEXT_MODEL", "muse-spark-test")
    monkeypatch.setenv("META_TRANSCRIBE_MODEL", "muse-voice-transcribe-test")


def _completion(content: Any) -> SimpleNamespace:
    return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=content))])


class _FakeCompletions:
    """Records create() kwargs; replays canned reply contents in order."""

    def __init__(self, replies: list[Any]):
        self.replies = list(replies)
        self.calls: list[dict[str, Any]] = []

    def create(self, **kwargs: Any) -> SimpleNamespace:
        self.calls.append(kwargs)
        return _completion(self.replies.pop(0))


def _patch_openai(monkeypatch, replies: list[Any]):
    """Replace meta_client.OpenAI; returns (constructor kwargs seen, completions fake)."""
    seen: dict[str, Any] = {}
    completions = _FakeCompletions(replies)

    def factory(**kwargs: Any) -> SimpleNamespace:
        seen.update(kwargs)
        return SimpleNamespace(chat=SimpleNamespace(completions=completions))

    monkeypatch.setattr(meta_client, "OpenAI", factory)
    return seen, completions


MESSAGES = [{"role": "user", "content": "extract"}]
SCHEMA = {"type": "object", "properties": {"nodes": {"type": "array"}}}


def test_chat_json_sends_env_model_and_schema_shape(env, monkeypatch):
    seen, completions = _patch_openai(monkeypatch, ['{"nodes": []}'])
    result = chat_json(MESSAGES, json_schema=SCHEMA, schema_name="analysis")
    assert result == {"nodes": []}
    assert seen == {"base_url": "https://api.meta.ai/v1", "api_key": "test-key"}
    assert completions.calls[0]["model"] == "muse-spark-test"
    assert completions.calls[0]["messages"] == MESSAGES
    assert completions.calls[0]["response_format"] == {
        "type": "json_schema",
        "json_schema": {"name": "analysis", "schema": SCHEMA},
    }


def test_chat_json_explicit_model_overrides_env(env, monkeypatch):
    _, completions = _patch_openai(monkeypatch, ['{"nodes": []}'])
    chat_json(MESSAGES, json_schema=SCHEMA, schema_name="analysis", model="other-model")
    assert completions.calls[0]["model"] == "other-model"


def test_chat_json_retries_once_on_invalid_json(env, monkeypatch):
    _, completions = _patch_openai(monkeypatch, ["not json {", '{"nodes": ["n1"]}'])
    result = chat_json(MESSAGES, json_schema=SCHEMA, schema_name="analysis")
    assert result == {"nodes": ["n1"]}
    assert len(completions.calls) == 2


def test_chat_json_retries_non_object_reply(env, monkeypatch):
    _, completions = _patch_openai(monkeypatch, ['["n1"]', '{"nodes": ["n1"]}'])
    assert chat_json(MESSAGES, json_schema=SCHEMA, schema_name="analysis") == {"nodes": ["n1"]}
    assert len(completions.calls) == 2


def test_chat_json_raises_after_two_bad_replies(env, monkeypatch):
    _, completions = _patch_openai(monkeypatch, ["junk", ""])
    with pytest.raises(MetaClientError):
        chat_json(MESSAGES, json_schema=SCHEMA, schema_name="analysis")
    assert len(completions.calls) == 2


def test_chat_json_missing_api_key_raises_without_network(env, monkeypatch):
    monkeypatch.delenv("META_API_KEY")
    with pytest.raises(MetaClientError):
        chat_json(MESSAGES, json_schema=SCHEMA, schema_name="analysis")


class _NodeList(BaseModel):
    nodes: list[str]


def test_chat_json_validated_parses_model(env, monkeypatch):
    _, completions = _patch_openai(monkeypatch, ['{"nodes": ["n1"]}'])
    result = chat_json_validated(MESSAGES, response_model=_NodeList)
    assert isinstance(result, _NodeList)
    assert result.nodes == ["n1"]
    sent = completions.calls[0]["response_format"]
    assert sent["type"] == "json_schema"
    assert sent["json_schema"]["name"] == "_NodeList"
    assert sent["json_schema"]["schema"] == _NodeList.model_json_schema()


def test_chat_json_validated_retries_on_schema_mismatch(env, monkeypatch):
    _, completions = _patch_openai(
        monkeypatch, ['{"wrong_field": []}', '{"nodes": ["n1"]}']
    )
    result = chat_json_validated(MESSAGES, response_model=_NodeList)
    assert result.nodes == ["n1"]
    assert len(completions.calls) == 2


def test_chat_json_validated_raises_after_two_failures(env, monkeypatch):
    _, completions = _patch_openai(monkeypatch, ['{"wrong_field": []}', "junk"])
    with pytest.raises(MetaClientError):
        chat_json_validated(MESSAGES, response_model=_NodeList)
    assert len(completions.calls) == 2


CANNED_TRANSCRIPTION = {
    "sessionId": "sess_1",
    "transcript": "Hello world. Hi there.",
    "audioDurationMs": 9000,
    "turns": [
        {"turnId": "t1", "startMs": 0, "endMs": 4000, "transcript": "Hello.", "speaker": "A"},
        {"turnId": "t2", "startMs": 4000, "endMs": 9000, "transcript": "Hi.", "speaker": "B"},
    ],
}


def _patch_httpx_post(monkeypatch, reply=None, error=None):
    seen: dict[str, Any] = {}

    def fake_post(url, **kwargs):
        seen["url"] = url
        seen.update(kwargs)
        if error is not None:
            raise error
        return SimpleNamespace(json=lambda: reply, raise_for_status=lambda: None)

    monkeypatch.setattr(httpx, "post", fake_post)
    return seen


def test_transcribe_wav_posts_multipart_shape(env, monkeypatch):
    seen = _patch_httpx_post(monkeypatch, reply=CANNED_TRANSCRIPTION)
    result = transcribe_wav(b"RIFFfake-wav-bytes", filename="debate.wav")
    assert seen["url"] == "https://api.meta.ai/v1/asr/transcribe"
    assert seen["headers"] == {"Authorization": "Bearer test-key"}
    request_filename, request_body, request_type = seen["files"]["request"]
    assert request_filename is None
    assert request_type == "application/json"
    assert json.loads(request_body) == {
        "model": "muse-voice-transcribe-test",
        "audioEncoding": "WAV",
        "mode": "DIARIZATION",
    }
    assert seen["files"]["audio"] == ("debate.wav", b"RIFFfake-wav-bytes", "audio/wav")
    assert isinstance(result, TranscriptionResult)
    assert result.sessionId == "sess_1"
    assert result.audioDurationMs == 9000
    assert [t.speaker for t in result.turns] == ["A", "B"]
    assert [t.startMs for t in result.turns] == [0, 4000]


def test_transcribe_wav_explicit_model_overrides_env(env, monkeypatch):
    seen = _patch_httpx_post(monkeypatch, reply=CANNED_TRANSCRIPTION)
    transcribe_wav(b"RIFFfake", model="other-transcribe-model")
    _, request_body, _ = seen["files"]["request"]
    assert json.loads(request_body)["model"] == "other-transcribe-model"


def test_transcribe_wav_wraps_http_error(env, monkeypatch):
    url = "https://api.meta.ai/v1/asr/transcribe"
    request = httpx.Request("POST", url)
    error = httpx.HTTPStatusError(
        "429 Too Many Requests", request=request, response=httpx.Response(429, request=request)
    )
    seen = _patch_httpx_post(monkeypatch, error=error)
    with pytest.raises(MetaClientError):
        transcribe_wav(b"RIFFfake")
    assert seen["url"] == url


def test_transcribe_wav_rejects_unexpected_reply_shape(env, monkeypatch):
    _patch_httpx_post(monkeypatch, reply={"unexpected": "shape"})
    with pytest.raises(MetaClientError):
        transcribe_wav(b"RIFFfake")


def test_transcribe_wav_missing_api_key_raises_without_network(env, monkeypatch):
    monkeypatch.delenv("META_API_KEY")
    with pytest.raises(MetaClientError):
        transcribe_wav(b"RIFFfake")
