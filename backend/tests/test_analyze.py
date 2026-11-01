"""Offline tests for POST /api/analyze (app.analyze).

The Meta text model is faked at the agent level by patching
``chat_json_validated`` in app.analyst, app.fallacy and
app.semantic_verifier; canned replies live in fixtures/analyst_reply.json,
fixtures/fallacy_reply.json and fixtures/semantic_verifier_reply.json, and
the transcript input in fixtures/sample_debate.json. No network is used.
The saved ``last_result.json`` is redirected to tmp_path so tests never
touch the real ``backend/data/`` file.
"""

import copy
import json
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from app import analyze as anmod
from app import analyst as amod
from app import fallacy as fmod
from app import semantic_verifier as smod
from app.main import app
from app.meta_client import MetaClientError
from app.schemas import DebateResult, Segment, Speaker

client = TestClient(app)

FIXTURES = Path(__file__).resolve().parents[2] / "fixtures"


def _load_input() -> dict[str, Any]:
    data = json.loads((FIXTURES / "sample_debate.json").read_text(encoding="utf-8"))
    return {
        "speakers": data["speakers"],
        "segments": data["segments"],
    }


def _fake_validated_factory(canned: dict[str, Any]):
    def fake(
        messages: list[dict[str, Any]],
        *,
        response_model: Any,
        schema_name: str | None = None,
        model: str | None = None,
        client: Any | None = None,
    ) -> Any:
        return response_model.model_validate(copy.deepcopy(canned))

    return fake


def _node_verdicts(ids: list[str], supported: bool = True) -> dict[str, Any]:
    return {
        "verdicts": [
            {"id": item_id, "supported": supported, "reason": "Canned verdict."}
            for item_id in ids
        ]
    }


def _node_ids() -> list[str]:
    canned = json.loads((FIXTURES / "analyst_reply.json").read_text(encoding="utf-8"))
    return [node["id"] for node in canned["nodes"]]


def _patch_pipeline(monkeypatch) -> None:
    """Fake all three model calls with good canned replies (all supported)."""
    analyst_canned = json.loads(
        (FIXTURES / "analyst_reply.json").read_text(encoding="utf-8")
    )
    fallacy_canned = json.loads(
        (FIXTURES / "fallacy_reply.json").read_text(encoding="utf-8")
    )
    fallacy_verdicts = json.loads(
        (FIXTURES / "semantic_verifier_reply.json").read_text(encoding="utf-8")
    )
    node_verdicts = _node_verdicts(_node_ids())
    monkeypatch.setattr(
        amod, "chat_json_validated", _fake_validated_factory(analyst_canned)
    )
    monkeypatch.setattr(
        fmod, "chat_json_validated", _fake_validated_factory(fallacy_canned)
    )

    def fake_semantic(
        messages: list[dict[str, Any]],
        *,
        response_model: Any,
        schema_name: str | None = None,
        model: str | None = None,
        client: Any | None = None,
    ) -> Any:
        if schema_name == smod.SCHEMA_NAME and messages:
            user_text = messages[1]["content"] if len(messages) > 1 else ""
            if "[f1]" in user_text or "Fallacies to judge" in user_text:
                return response_model.model_validate(copy.deepcopy(fallacy_verdicts))
            return response_model.model_validate(copy.deepcopy(node_verdicts))
        return response_model.model_validate(copy.deepcopy(node_verdicts))

    monkeypatch.setattr(smod, "chat_json_validated", fake_semantic)


def test_analyze_runs_full_pipeline_and_saves(monkeypatch, tmp_path):
    saved = tmp_path / "last_result.json"
    monkeypatch.setattr(anmod, "LAST_RESULT_PATH", saved)
    _patch_pipeline(monkeypatch)
    response = client.post("/api/analyze", json=_load_input())
    assert response.status_code == 200, response.text
    body = response.json()
    result = DebateResult.model_validate(body)
    assert len(result.nodes) == 9
    assert len(result.edges) == 8
    assert len(result.fallacies) == 3
    assert [s["id"] for s in body["speakers"]] == ["S1", "S2"]
    assert len(body["segments"]) == 11
    # Good canned quotes + timestamps survive both verifiers.
    assert all(node.verified is True for node in result.nodes)
    assert all(item.verified is True for item in result.fallacies)
    # The result is saved for fast demo reloads and matches the response.
    assert saved.exists()
    assert json.loads(saved.read_text(encoding="utf-8")) == body


def test_analyze_deterministic_verifier_downgrades_invented_quote(
    monkeypatch, tmp_path
):
    monkeypatch.setattr(anmod, "LAST_RESULT_PATH", tmp_path / "last_result.json")
    _patch_pipeline(monkeypatch)
    broken = json.loads((FIXTURES / "analyst_reply.json").read_text(encoding="utf-8"))
    broken["nodes"][0]["quote"] = "Remote work cures every disease known to science."
    monkeypatch.setattr(amod, "chat_json_validated", _fake_validated_factory(broken))
    response = client.post("/api/analyze", json=_load_input())
    assert response.status_code == 200, response.text
    by_id = {node["id"]: node for node in response.json()["nodes"]}
    assert by_id["n1"]["verified"] is False
    assert by_id["n2"]["verified"] is True


def test_analyze_semantic_verifier_downgrades_unsupported_label(
    monkeypatch, tmp_path
):
    monkeypatch.setattr(anmod, "LAST_RESULT_PATH", tmp_path / "last_result.json")
    analyst_canned = json.loads(
        (FIXTURES / "analyst_reply.json").read_text(encoding="utf-8")
    )
    fallacy_canned = json.loads(
        (FIXTURES / "fallacy_reply.json").read_text(encoding="utf-8")
    )
    fallacy_verdicts = json.loads(
        (FIXTURES / "semantic_verifier_reply.json").read_text(encoding="utf-8")
    )
    node_verdicts = _node_verdicts(_node_ids())
    node_verdicts["verdicts"][1]["supported"] = False
    node_verdicts["verdicts"][1]["reason"] = "The quote says nothing about that."
    monkeypatch.setattr(
        amod, "chat_json_validated", _fake_validated_factory(analyst_canned)
    )
    monkeypatch.setattr(
        fmod, "chat_json_validated", _fake_validated_factory(fallacy_canned)
    )

    def fake_semantic(
        messages: list[dict[str, Any]],
        *,
        response_model: Any,
        schema_name: str | None = None,
        model: str | None = None,
        client: Any | None = None,
    ) -> Any:
        user_text = messages[1]["content"] if len(messages) > 1 else ""
        if "[f1]" in user_text or "Fallacies to judge" in user_text:
            return response_model.model_validate(copy.deepcopy(fallacy_verdicts))
        return response_model.model_validate(copy.deepcopy(node_verdicts))

    monkeypatch.setattr(smod, "chat_json_validated", fake_semantic)
    response = client.post("/api/analyze", json=_load_input())
    assert response.status_code == 200, response.text
    by_id = {node["id"]: node for node in response.json()["nodes"]}
    assert by_id["n2"]["verified"] is False
    assert by_id["n1"]["verified"] is True


def test_analyze_rejects_empty_segments(monkeypatch, tmp_path):
    monkeypatch.setattr(anmod, "LAST_RESULT_PATH", tmp_path / "last_result.json")
    called = {"count": 0}

    def refuse(*args: Any, **kwargs: Any) -> Any:
        called["count"] += 1
        raise AssertionError("model must not be called without segments")

    monkeypatch.setattr(amod, "chat_json_validated", refuse)
    monkeypatch.setattr(fmod, "chat_json_validated", refuse)
    monkeypatch.setattr(smod, "chat_json_validated", refuse)
    payload = _load_input()
    payload["segments"] = []
    response = client.post("/api/analyze", json=payload)
    assert response.status_code == 400, response.text
    assert called["count"] == 0


def test_analyze_model_error_is_502(monkeypatch, tmp_path):
    monkeypatch.setattr(anmod, "LAST_RESULT_PATH", tmp_path / "last_result.json")

    def fail(*args: Any, **kwargs: Any) -> Any:
        raise MetaClientError("chat model returned invalid JSON twice")

    monkeypatch.setattr(amod, "chat_json_validated", fail)
    response = client.post("/api/analyze", json=_load_input())
    assert response.status_code == 502, response.text


def test_analyze_semantic_failure_degrades_to_deterministic(monkeypatch, tmp_path):
    """A semantic-verifier outage must not lose the whole analysis."""
    monkeypatch.setattr(anmod, "LAST_RESULT_PATH", tmp_path / "last_result.json")
    analyst_canned = json.loads(
        (FIXTURES / "analyst_reply.json").read_text(encoding="utf-8")
    )
    fallacy_canned = json.loads(
        (FIXTURES / "fallacy_reply.json").read_text(encoding="utf-8")
    )
    monkeypatch.setattr(
        amod, "chat_json_validated", _fake_validated_factory(analyst_canned)
    )
    monkeypatch.setattr(
        fmod, "chat_json_validated", _fake_validated_factory(fallacy_canned)
    )

    def fail(*args: Any, **kwargs: Any) -> Any:
        raise MetaClientError("semantic verifier unavailable")

    monkeypatch.setattr(smod, "chat_json_validated", fail)
    response = client.post("/api/analyze", json=_load_input())
    assert response.status_code == 200, response.text
    result = DebateResult.model_validate(response.json())
    assert len(result.nodes) == 9
    # Deterministic flags survive: good canned quotes stay verified.
    assert all(node.verified is True for node in result.nodes)
    assert len(result.fallacies) == 3


def test_analyze_fallacy_failure_degrades_to_empty_fallacies(
    monkeypatch, tmp_path
):
    """A FallacyHunter outage returns the graph with no fallacy flags."""
    monkeypatch.setattr(anmod, "LAST_RESULT_PATH", tmp_path / "last_result.json")
    analyst_canned = json.loads(
        (FIXTURES / "analyst_reply.json").read_text(encoding="utf-8")
    )
    monkeypatch.setattr(
        amod, "chat_json_validated", _fake_validated_factory(analyst_canned)
    )

    def fail(*args: Any, **kwargs: Any) -> Any:
        raise MetaClientError("fallacy hunter unavailable")

    monkeypatch.setattr(fmod, "chat_json_validated", fail)
    monkeypatch.setattr(
        smod,
        "chat_json_validated",
        _fake_validated_factory(_node_verdicts(_node_ids())),
    )
    response = client.post("/api/analyze", json=_load_input())
    assert response.status_code == 200, response.text
    result = DebateResult.model_validate(response.json())
    assert len(result.nodes) == 9
    assert result.fallacies == []


def test_save_result_is_atomic_and_leaves_no_tmp(tmp_path):
    from app.analyze import save_result

    result = DebateResult.model_validate(_load_input() | {
        "nodes": [], "edges": [], "fallacies": [],
    })
    target = tmp_path / "nested" / "last_result.json"
    saved = save_result(result, target)
    assert saved == target
    assert DebateResult.model_validate_json(target.read_text(encoding="utf-8")) == result
    assert not list((tmp_path / "nested").glob("*.tmp"))
    # Overwriting an existing result (the demo file) replaces it cleanly.
    save_result(result, target)
    assert DebateResult.model_validate_json(target.read_text(encoding="utf-8")) == result
    assert not list((tmp_path / "nested").glob("*.tmp"))


def test_run_analysis_saves_contract_json(monkeypatch, tmp_path):
    saved = tmp_path / "nested" / "last_result.json"
    monkeypatch.setattr(anmod, "LAST_RESULT_PATH", saved)
    _patch_pipeline(monkeypatch)
    data = json.loads((FIXTURES / "sample_debate.json").read_text(encoding="utf-8"))
    speakers = [Speaker.model_validate(item) for item in data["speakers"]]
    segments = [Segment.model_validate(item) for item in data["segments"]]
    result = anmod.run_analysis(speakers, segments)
    assert isinstance(result, DebateResult)
    assert DebateResult.model_validate(
        json.loads(saved.read_text(encoding="utf-8"))
    ) == result
