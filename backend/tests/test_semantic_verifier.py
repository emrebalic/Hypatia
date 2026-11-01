"""Offline tests for the semantic verifier agent (app.semantic_verifier).

The Meta text model is faked by patching
app.semantic_verifier.chat_json_validated; the fallacy-verdict fixture lives
in fixtures/semantic_verifier_reply.json, node verdicts are built inline,
and transcript inputs come from fixtures/sample_debate.json. No network is
used. Already-unverified items are never sent to the model and stay False;
the model can keep or downgrade, never upgrade.
"""

import copy
import json
from pathlib import Path
from typing import Any

import pytest

from app import semantic_verifier as smod
from app.meta_client import MetaClientError
from app.schemas import Fallacy, Node, Segment, Speaker
from app.semantic_verifier import (
    SemanticReply,
    build_fallacy_messages,
    build_node_messages,
    load_semantic_prompt,
    verify_fallacies_semantic,
    verify_nodes_semantic,
)

FIXTURES = Path(__file__).resolve().parents[2] / "fixtures"


def _load() -> tuple[list[Speaker], list[Segment], list[Node], list[Fallacy]]:
    data = json.loads((FIXTURES / "sample_debate.json").read_text(encoding="utf-8"))
    speakers = [Speaker.model_validate(item) for item in data["speakers"]]
    segments = [Segment.model_validate(item) for item in data["segments"]]
    nodes = [Node.model_validate(item) for item in data["nodes"]]
    fallacies = [Fallacy.model_validate(item) for item in data["fallacies"]]
    return speakers, segments, nodes, fallacies


def _canned_fallacy_reply() -> dict[str, Any]:
    return json.loads(
        (FIXTURES / "semantic_verifier_reply.json").read_text(encoding="utf-8")
    )


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


def _node_verdicts(ids: list[str], supported: bool = True) -> dict[str, Any]:
    return {
        "verdicts": [
            {"id": item_id, "supported": supported, "reason": "Canned verdict."}
            for item_id in ids
        ]
    }


def test_supported_nodes_stay_verified(monkeypatch):
    _, segments, nodes, _ = _load()
    subset = nodes[:3]
    seen: dict[str, Any] = {}
    monkeypatch.setattr(
        smod,
        "chat_json_validated",
        _fake_validated_factory(_node_verdicts(["n1", "n2", "n3"]), seen),
    )
    checked = verify_nodes_semantic(subset, segments)
    assert all(node.verified is True for node in checked)
    assert seen["response_model"] is SemanticReply
    assert seen["schema_name"] == smod.SCHEMA_NAME


def test_unsupported_node_paraphrase_is_downgraded(monkeypatch):
    _, segments, nodes, _ = _load()
    subset = copy.deepcopy(nodes[:3])
    canned = _node_verdicts(["n1", "n2", "n3"])
    canned["verdicts"][1]["supported"] = False
    canned["verdicts"][1]["reason"] = "The quote says nothing about controlling anything."
    monkeypatch.setattr(smod, "chat_json_validated", _fake_validated_factory(canned, {}))
    checked = verify_nodes_semantic(subset, segments)
    by_id = {node.id: node for node in checked}
    assert by_id["n2"].verified is False
    assert by_id["n1"].verified is True
    assert by_id["n3"].verified is True
    # Inputs are not mutated.
    assert all(node.verified is True for node in subset)


def test_unverified_nodes_are_not_sent_and_never_upgraded(monkeypatch):
    _, segments, nodes, _ = _load()
    subset = copy.deepcopy(nodes[:3])
    subset[0] = subset[0].model_copy(update={"verified": False})
    seen: dict[str, Any] = {}
    # The stray n1 verdict must not upgrade it: ineligible items stay False.
    canned = {
        "verdicts": [
            {"id": "n1", "supported": True, "reason": "Stray verdict."},
            {"id": "n2", "supported": True, "reason": "Canned verdict."},
            {"id": "n3", "supported": True, "reason": "Canned verdict."},
        ]
    }
    monkeypatch.setattr(
        smod, "chat_json_validated", _fake_validated_factory(canned, seen)
    )
    checked = verify_nodes_semantic(subset, segments)
    user_text = seen["messages"][1]["content"]
    assert "[n1]" not in user_text
    assert "[n2]" in user_text and "[n3]" in user_text
    by_id = {node.id: node for node in checked}
    assert by_id["n1"].verified is False
    assert by_id["n2"].verified is True


def test_node_messages_carry_prompt_transcript_and_items(monkeypatch):
    speakers, segments, nodes, _ = _load()
    seen: dict[str, Any] = {}
    monkeypatch.setattr(
        smod,
        "chat_json_validated",
        _fake_validated_factory(_node_verdicts(["n1", "n2"]), seen),
    )
    verify_nodes_semantic(nodes[:2], segments, speakers)
    messages = seen["messages"]
    assert [message["role"] for message in messages] == ["system", "user"]
    assert messages[0]["content"] == load_semantic_prompt()
    assert "support" in messages[0]["content"].lower()
    user_text = messages[1]["content"]
    for segment in segments:
        assert segment.id in user_text
    assert "[n1]" in user_text and "[n2]" in user_text
    assert "S1" in user_text


def test_supported_fallacies_stay_verified(monkeypatch):
    speakers, segments, nodes, fallacies = _load()
    monkeypatch.setattr(
        smod, "chat_json_validated", _fake_validated_factory(_canned_fallacy_reply(), {})
    )
    checked = verify_fallacies_semantic(fallacies, segments, nodes, speakers)
    assert all(item.verified is True for item in checked)


def test_unsupported_fallacy_label_is_downgraded(monkeypatch):
    speakers, segments, nodes, fallacies = _load()
    inputs = copy.deepcopy(fallacies)
    canned = _canned_fallacy_reply()
    canned["verdicts"][1]["supported"] = False
    canned["verdicts"][1]["reason"] = "Anecdotal sample, not a hasty generalization."
    monkeypatch.setattr(
        smod, "chat_json_validated", _fake_validated_factory(canned, {})
    )
    checked = verify_fallacies_semantic(inputs, segments, nodes, speakers)
    by_id = {item.id: item for item in checked}
    assert by_id["f2"].verified is False
    assert by_id["f1"].verified is True
    assert by_id["f3"].verified is True
    assert all(item.verified is True for item in inputs)


def test_missing_verdict_keeps_and_unknown_verdict_ignored(monkeypatch):
    _, segments, _, fallacies = _load()
    canned = {
        "verdicts": [
            {"id": "f1", "supported": True, "reason": "Canned verdict."},
            {"id": "fX", "supported": False, "reason": "Unknown item."},
        ]
    }
    monkeypatch.setattr(smod, "chat_json_validated", _fake_validated_factory(canned, {}))
    checked = verify_fallacies_semantic(fallacies, segments)
    # f2/f3 have no verdict: kept. fX matches nothing: ignored.
    assert all(item.verified is True for item in checked)
    assert {item.id for item in checked} == {"f1", "f2", "f3"}


def test_no_model_call_when_nothing_eligible(monkeypatch):
    _, segments, nodes, _ = _load()
    inputs = [node.model_copy(update={"verified": False}) for node in nodes[:2]]
    called = {"count": 0}

    def refuse(*args: Any, **kwargs: Any) -> Any:
        called["count"] += 1
        raise AssertionError("model must not be called without eligible items")

    monkeypatch.setattr(smod, "chat_json_validated", refuse)
    checked = verify_nodes_semantic(inputs, segments)
    assert [node.verified for node in checked] == [False, False]
    assert called["count"] == 0
    checked_f = verify_fallacies_semantic(
        [f.model_copy(update={"verified": False}) for f in _load()[3][:1]], segments
    )
    assert [item.verified for item in checked_f] == [False]
    assert called["count"] == 0


def test_empty_lists_skip_model(monkeypatch):
    _, segments, _, _ = _load()
    called = {"count": 0}

    def refuse(*args: Any, **kwargs: Any) -> Any:
        called["count"] += 1
        raise AssertionError("model must not be called for empty lists")

    monkeypatch.setattr(smod, "chat_json_validated", refuse)
    assert verify_nodes_semantic([], segments) == []
    assert verify_fallacies_semantic([], segments) == []
    assert called["count"] == 0


def test_semantic_errors_propagate(monkeypatch):
    _, segments, nodes, _ = _load()

    def fail(*args: Any, **kwargs: Any) -> Any:
        raise MetaClientError("chat model returned invalid JSON twice")

    monkeypatch.setattr(smod, "chat_json_validated", fail)
    with pytest.raises(MetaClientError):
        verify_nodes_semantic(nodes[:1], segments)
    with pytest.raises(MetaClientError):
        verify_fallacies_semantic(_load()[3][:1], segments)


def test_canned_fixture_and_prompt_shape():
    reply = SemanticReply.model_validate(_canned_fallacy_reply())
    assert {verdict.id for verdict in reply.verdicts} == {"f1", "f2", "f3"}
    assert all(verdict.supported is True for verdict in reply.verdicts)
    assert all(verdict.reason.strip() for verdict in reply.verdicts)
    _, segments, nodes, fallacies = _load()
    assert build_node_messages(nodes, segments)[0]["content"].strip()
    assert build_fallacy_messages(fallacies, segments)[0]["content"].strip()
