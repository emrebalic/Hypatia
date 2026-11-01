"""Offline tests for the FallacyHunter agent (app.fallacy).

The Meta text model is faked by patching app.fallacy.chat_json_validated;
the canned reply lives in fixtures/fallacy_reply.json and the transcript +
nodes input in fixtures/sample_debate.json. No network is used. The hunter
runs its output through the deterministic verifier, so broken canned replies
must come back with verified=False.
"""

import copy
import json
from pathlib import Path
from typing import Any

import pytest

from app import fallacy as fmod
from app.fallacy import (
    FallacyReply,
    build_fallacy_messages,
    hunt_fallacies,
    load_fallacy_prompt,
)
from app.meta_client import MetaClientError
from app.schemas import Fallacy, Node, Segment, Speaker

FIXTURES = Path(__file__).resolve().parents[2] / "fixtures"


def _load_inputs() -> tuple[list[Speaker], list[Segment], list[Node]]:
    data = json.loads((FIXTURES / "sample_debate.json").read_text(encoding="utf-8"))
    speakers = [Speaker.model_validate(item) for item in data["speakers"]]
    segments = [Segment.model_validate(item) for item in data["segments"]]
    nodes = [Node.model_validate(item) for item in data["nodes"]]
    return speakers, segments, nodes


def _canned_reply() -> dict[str, Any]:
    return json.loads((FIXTURES / "fallacy_reply.json").read_text(encoding="utf-8"))


def _fake_validated_factory(canned: dict[str, Any], seen: dict[str, Any]):
    def fake(
        messages: list[dict[str, Any]],
        *,
        response_model: Any,
        schema_name: str | None = None,
        model: str | None = None,
        client: Any | None = None,
    ) -> Any:
        seen["messages"] = messages
        seen["response_model"] = response_model
        seen["schema_name"] = schema_name
        return response_model.model_validate(copy.deepcopy(canned))

    return fake


def test_hunt_returns_contract_fallacies(monkeypatch):
    speakers, segments, nodes = _load_inputs()
    seen: dict[str, Any] = {}
    monkeypatch.setattr(
        fmod, "chat_json_validated", _fake_validated_factory(_canned_reply(), seen)
    )
    fallacies = hunt_fallacies(speakers, segments, nodes)
    assert len(fallacies) == 3
    assert all(isinstance(item, Fallacy) for item in fallacies)
    # Good canned quotes + timestamps survive the deterministic verifier.
    assert all(item.verified is True for item in fallacies)
    by_id = {item.id: item for item in fallacies}
    assert by_id["f1"].node_id == "n5"
    assert by_id["f1"].name == "Straw man"
    assert by_id["f2"].name == "Hasty generalization"
    assert by_id["f3"].name == "Ad hominem (circumstantial)"
    assert seen["response_model"] is FallacyReply
    assert seen["schema_name"] == fmod.SCHEMA_NAME


def test_hunt_sends_prompt_file_and_full_context(monkeypatch):
    speakers, segments, nodes = _load_inputs()
    seen: dict[str, Any] = {}
    monkeypatch.setattr(
        fmod, "chat_json_validated", _fake_validated_factory(_canned_reply(), seen)
    )
    hunt_fallacies(speakers, segments, nodes)
    messages = seen["messages"]
    assert [message["role"] for message in messages] == ["system", "user"]
    assert messages[0]["content"] == load_fallacy_prompt()
    assert "verbatim" in messages[0]["content"].lower()
    user_text = messages[1]["content"]
    for segment in segments:
        assert segment.id in user_text
        assert segment.text in user_text
    for node in nodes:
        assert node.id in user_text
    assert "S1" in user_text and "S2" in user_text


def test_invented_quote_fails_verifier(monkeypatch):
    speakers, segments, nodes = _load_inputs()
    canned = _canned_reply()
    canned["fallacies"][0]["quote"] = "Nobody ever said anything about meeting anyone."
    monkeypatch.setattr(
        fmod, "chat_json_validated", _fake_validated_factory(canned, {})
    )
    by_id = {item.id: item for item in hunt_fallacies(speakers, segments, nodes)}
    assert by_id["f1"].verified is False
    assert by_id["f2"].verified is True
    assert by_id["f3"].verified is True


def test_timestamp_outside_node_segment_fails_verifier(monkeypatch):
    speakers, segments, nodes = _load_inputs()
    canned = _canned_reply()
    canned["fallacies"][1]["start"] = 999.0
    monkeypatch.setattr(
        fmod, "chat_json_validated", _fake_validated_factory(canned, {})
    )
    by_id = {item.id: item for item in hunt_fallacies(speakers, segments, nodes)}
    assert by_id["f2"].verified is False
    assert by_id["f1"].verified is True


def test_hunt_rejects_empty_segments(monkeypatch):
    speakers, _, nodes = _load_inputs()
    called = {"count": 0}

    def refuse(*args: Any, **kwargs: Any) -> Any:
        called["count"] += 1
        raise AssertionError("model must not be called without segments")

    monkeypatch.setattr(fmod, "chat_json_validated", refuse)
    with pytest.raises(ValueError):
        hunt_fallacies(speakers, [], nodes)
    assert called["count"] == 0


def test_hunt_with_no_nodes_skips_model(monkeypatch):
    speakers, segments, _ = _load_inputs()
    called = {"count": 0}

    def refuse(*args: Any, **kwargs: Any) -> Any:
        called["count"] += 1
        raise AssertionError("model must not be called without nodes")

    monkeypatch.setattr(fmod, "chat_json_validated", refuse)
    assert hunt_fallacies(speakers, segments, []) == []
    assert called["count"] == 0


def test_hunt_propagates_model_error(monkeypatch):
    speakers, segments, nodes = _load_inputs()

    def fail(*args: Any, **kwargs: Any) -> Any:
        raise MetaClientError("chat model returned invalid JSON twice")

    monkeypatch.setattr(fmod, "chat_json_validated", fail)
    with pytest.raises(MetaClientError):
        hunt_fallacies(speakers, segments, nodes)


def test_canned_fixture_matches_sample_transcript():
    """The canned reply is hunter-quality: quotes verbatim, starts in-segment."""
    data = json.loads((FIXTURES / "sample_debate.json").read_text(encoding="utf-8"))
    segments = {seg["id"]: seg for seg in data["segments"]}
    nodes = {node["id"]: node for node in data["nodes"]}
    reply = FallacyReply.model_validate(_canned_reply())
    assert len({item.id for item in reply.fallacies}) == len(reply.fallacies)
    for item in reply.fallacies:
        node = nodes[item.node_id]
        assert item.node_id in nodes
        for segment_id in node["segment_ids"]:
            segment = segments[segment_id]
            assert item.quote.lower() in segment["text"].lower()
            assert segment["start"] <= item.start <= segment["end"]
    assert build_fallacy_messages(*_load_inputs())[0]["content"].strip()
