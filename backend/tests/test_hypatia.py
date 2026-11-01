"""Tests for the Hypatia proof check (task 24).

The Meta text model is faked by patching app.philosopher.chat_json_validated;
the canned reply lives in fixtures/hypatia_reply.json and the debate input in
fixtures/sample_debate.json. No network is used.

Hypatia must, for each side, list the definitions and assumptions its argument
depends on, walk the steps in order marking each ``holds`` or ``breaks`` with
the reason and node ids, name no overall winner, and end with what both sides
have actually established. No quotes or writings are ever attributed to her;
none survive.
"""

import copy
import json
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from app import philosopher as pmod
from app.philosopher import (
    PhilosopherReply,
    ask_philosopher,
    load_philosopher_prompt,
)
from app.main import app
from app.schemas import DebateResult

client = TestClient(app)

FIXTURES = Path(__file__).resolve().parents[2] / "fixtures"

BANNED_WINNER_WORDS = (
    "argued better",
    "argues better",
    "is right",
    "is true",
)


def _load_result() -> DebateResult:
    return DebateResult.model_validate(
        json.loads((FIXTURES / "sample_debate.json").read_text(encoding="utf-8"))
    )


def _load_canned() -> dict[str, Any]:
    return copy.deepcopy(
        json.loads((FIXTURES / "hypatia_reply.json").read_text(encoding="utf-8"))
    )


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


def test_hypatia_prompt_teaches_proof_check_and_no_winner():
    prompt = load_philosopher_prompt("hypatia")
    lowered = prompt.lower()
    assert "definition" in lowered
    assert "assumption" in lowered
    assert "holds" in lowered
    assert "breaks" in lowered
    assert "node_ids" in prompt
    assert "no overall winner" in lowered
    assert "established" in lowered
    assert "did not survive" in lowered
    assert "never attribute" in lowered
    assert "Sophistical" not in prompt


def test_hypatia_prompt_states_will_not_rules():
    prompt = load_philosopher_prompt("hypatia")
    lowered = prompt.lower()
    assert "will not" in lowered
    assert "name a winner" in lowered
    assert "attribute any quote" in lowered
    assert "paraphrase" in lowered


def test_hypatia_fixture_checks_both_sides_step_by_step():
    result = _load_result()
    known = {node.id for node in result.nodes}
    speaker_of = {node.id: node.speaker for node in result.nodes}
    reply = PhilosopherReply.model_validate(_load_canned())
    assert reply.philosopher == "hypatia"
    assert len(reply.points) >= 4
    for point in reply.points:
        assert point.node_ids
        assert set(point.node_ids) <= known
        assert "holds" in point.text.lower() or "breaks" in point.text.lower()
    combined = "\n".join(point.text for point in reply.points).lower()
    assert "definition" in combined
    assert "assumption" in combined
    cited = {nid for point in reply.points for nid in point.node_ids}
    speakers = {speaker_of[nid] for nid in cited}
    assert {"S1", "S2"} <= speakers
    per_side = {"S1": 0, "S2": 0}
    for point in reply.points:
        for side in {speaker_of[nid] for nid in point.node_ids}:
            per_side[side] += 1
    assert per_side["S1"] >= 2
    assert per_side["S2"] >= 2
    whole = (reply.summary + "\n" + combined).lower()
    assert "no overall winner" in whole
    for banned in BANNED_WINNER_WORDS:
        assert banned not in whole
    assert "hypatia" not in whole
    assert "established" in reply.summary.lower()


def test_ask_philosopher_accepts_hypatia_fixture(monkeypatch):
    result = _load_result()
    canned = _load_canned()
    monkeypatch.setattr(
        pmod, "chat_json_validated", _fake_validated_factory(canned)
    )
    reply = ask_philosopher("hypatia", result)
    assert reply.philosopher == "hypatia"
    assert "established" in reply.summary.lower()
    assert all(
        "holds" in point.text.lower() or "breaks" in point.text.lower()
        for point in reply.points
    )


def test_hypatia_endpoint_returns_proof_check(monkeypatch):
    canned = _load_canned()
    monkeypatch.setattr(
        pmod, "chat_json_validated", _fake_validated_factory(canned)
    )
    body = {
        "philosopher": "hypatia",
        "result": json.loads(
            (FIXTURES / "sample_debate.json").read_text(encoding="utf-8")
        ),
    }
    response = client.post("/api/philosopher", json=body)
    assert response.status_code == 200, response.text
    reply = PhilosopherReply.model_validate(response.json())
    assert reply.philosopher == "hypatia"
    assert len(reply.points) >= 4
    assert "established" in reply.summary.lower()
