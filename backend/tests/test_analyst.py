"""Offline tests for the analyst agent (app.analyst).

The Meta text model is faked by patching app.analyst.chat_json_validated;
the canned reply lives in fixtures/analyst_reply.json and the transcript
input in fixtures/sample_debate.json. No network is used.
"""

import json
from pathlib import Path
from typing import Any

import pytest

from app import analyst as amod
from app.analyst import (
    AnalystReply,
    analyze_transcript,
    build_analyst_messages,
    load_analyst_prompt,
)
from app.meta_client import MetaClientError
from app.schemas import Edge, Node, Segment, Speaker

FIXTURES = Path(__file__).resolve().parents[2] / "fixtures"


def _load_transcript_input() -> tuple[list[Speaker], list[Segment]]:
    data = json.loads((FIXTURES / "sample_debate.json").read_text(encoding="utf-8"))
    speakers = [Speaker.model_validate(item) for item in data["speakers"]]
    segments = [Segment.model_validate(item) for item in data["segments"]]
    return speakers, segments


def _canned_reply() -> dict[str, Any]:
    return json.loads((FIXTURES / "analyst_reply.json").read_text(encoding="utf-8"))


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
        return response_model.model_validate(canned)

    return fake


def test_analyze_returns_contract_nodes_and_edges(monkeypatch):
    speakers, segments = _load_transcript_input()
    seen: dict[str, Any] = {}
    monkeypatch.setattr(
        amod, "chat_json_validated", _fake_validated_factory(_canned_reply(), seen)
    )
    nodes, edges = analyze_transcript(speakers, segments)
    assert len(nodes) == 9
    assert len(edges) == 8
    assert all(isinstance(node, Node) for node in nodes)
    assert all(isinstance(edge, Edge) for edge in edges)
    # The analyst stamps verified=True; the task-8 verifier owns downgrades.
    assert all(node.verified is True for node in nodes)
    by_id = {node.id: node for node in nodes}
    assert by_id["n1"].type == "conclusion"
    assert by_id["n4"].type == "rebuttal"
    assert by_id["n9"].segment_ids == ["seg_11"]
    assert {edge.relation for edge in edges} <= {"supports", "attacks"}
    assert seen["response_model"] is AnalystReply


def test_analyze_snaps_cleaned_quote_to_exact_transcript_words(monkeypatch):
    # The model tends to clean up stutters; grounding must restore the
    # exact spoken words and correct segment/speaker/start from them.
    speakers = [Speaker(id="S1", label="Speaker 1")]
    segments = [
        Segment(
            id="seg_1",
            speaker="S1",
            start=10.0,
            end=20.0,
            text="well well I I think remote work should should be the default here",
        )
    ]
    canned = {
        "nodes": [
            {
                "id": "n1",
                "type": "claim",
                "speaker": "S9",
                "text": "Remote work should be the default.",
                "quote": "I think remote work should be the default",
                "start": 999.0,
                "segment_ids": ["seg_99"],
            }
        ],
        "edges": [],
    }
    monkeypatch.setattr(
        amod, "chat_json_validated", _fake_validated_factory(canned, {})
    )
    nodes, _ = analyze_transcript(speakers, segments)
    assert len(nodes) == 1
    node = nodes[0]
    assert node.quote == "I think remote work should should be the default"
    assert node.segment_ids == ["seg_1"]
    assert node.speaker == "S1"
    assert node.start == 10.0


def test_analyze_drops_dangling_and_self_edges(monkeypatch):
    speakers, segments = _load_transcript_input()
    canned = _canned_reply()
    canned["edges"] = canned["edges"] + [
        {"source": "n1", "target": "ghost", "relation": "supports"},
        {"source": "ghost", "target": "n1", "relation": "attacks"},
        {"source": "n1", "target": "n1", "relation": "supports"},
    ]
    monkeypatch.setattr(
        amod, "chat_json_validated", _fake_validated_factory(canned, {})
    )
    nodes, edges = analyze_transcript(speakers, segments)
    known = {node.id for node in nodes}
    assert len(edges) == 8
    assert all(edge.source in known and edge.target in known for edge in edges)
    assert all(edge.source != edge.target for edge in edges)


def test_analyze_sends_prompt_file_and_full_transcript(monkeypatch):
    speakers, segments = _load_transcript_input()
    seen: dict[str, Any] = {}
    monkeypatch.setattr(
        amod, "chat_json_validated", _fake_validated_factory(_canned_reply(), seen)
    )
    analyze_transcript(speakers, segments)
    messages = seen["messages"]
    assert [message["role"] for message in messages] == ["system", "user"]
    assert messages[0]["content"] == load_analyst_prompt()
    assert "verbatim" in messages[0]["content"].lower()
    user_text = messages[1]["content"]
    for segment in segments:
        assert segment.id in user_text
        assert segment.text in user_text
    assert "S1" in user_text and "S2" in user_text


def test_analyze_rejects_empty_segments(monkeypatch):
    speakers, _ = _load_transcript_input()
    called = {"count": 0}

    def refuse(*args: Any, **kwargs: Any) -> Any:
        called["count"] += 1
        raise AssertionError("model must not be called without segments")

    monkeypatch.setattr(amod, "chat_json_validated", refuse)
    with pytest.raises(ValueError):
        analyze_transcript(speakers, [])
    assert called["count"] == 0


def test_analyze_propagates_model_error(monkeypatch):
    speakers, segments = _load_transcript_input()

    def fail(*args: Any, **kwargs: Any) -> Any:
        raise MetaClientError("chat model returned invalid JSON twice")

    monkeypatch.setattr(amod, "chat_json_validated", fail)
    with pytest.raises(MetaClientError):
        analyze_transcript(speakers, segments)


def test_canned_fixture_matches_sample_transcript():
    """The canned reply is analyst-quality: quotes verbatim, starts in-segment."""
    data = json.loads((FIXTURES / "sample_debate.json").read_text(encoding="utf-8"))
    segments = {seg["id"]: seg for seg in data["segments"]}
    reply = AnalystReply.model_validate(_canned_reply())
    node_ids = {node.id for node in reply.nodes}
    assert len(node_ids) == len(reply.nodes)
    for node in reply.nodes:
        for segment_id in node.segment_ids:
            segment = segments[segment_id]
            assert node.quote.lower() in segment["text"].lower()
            assert segment["start"] <= node.start <= segment["end"]
    for edge in reply.edges:
        assert edge.source in node_ids
        assert edge.target in node_ids
    assert build_analyst_messages(*_load_transcript_input())[0]["content"].strip()
