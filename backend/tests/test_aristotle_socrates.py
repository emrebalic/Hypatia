"""Tests for the Aristotle + Socrates methods (task 17).

The Meta text model is faked by patching app.philosopher.chat_json_validated;
canned replies live in fixtures/aristotle_reply.json and
fixtures/socrates_reply.json and the debate input in
fixtures/sample_debate.json. No network is used.

Aristotle must give a verdict on who argued better using syllogistic
structure and his fallacy categories; Socrates must give no verdict and
ask 2-3 probing questions per side targeting the weakest premise.
"""

import copy
import json
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from app import philosopher as pmod
from app.main import app
from app.philosopher import (
    PhilosopherReply,
    ask_philosopher,
    load_philosopher_prompt,
)
from app.schemas import DebateResult

client = TestClient(app)

FIXTURES = Path(__file__).resolve().parents[2] / "fixtures"

BANNED_VERDICT_WORDS = (
    "winner",
    "verdict",
    "argued better",
    "argues better",
    "is right",
)


def _load_result() -> DebateResult:
    return DebateResult.model_validate(
        json.loads((FIXTURES / "sample_debate.json").read_text(encoding="utf-8"))
    )


def _load_canned(name: str) -> dict[str, Any]:
    return copy.deepcopy(
        json.loads((FIXTURES / name).read_text(encoding="utf-8"))
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


def test_aristotle_prompt_teaches_syllogism_fallacy_and_verdict():
    prompt = load_philosopher_prompt("aristotle")
    lowered = prompt.lower()
    assert "syllogis" in lowered
    assert "Sophistical Refutations" in prompt
    assert "fallac" in lowered
    assert "verdict" in lowered
    assert "argued better" in lowered
    assert "node_ids" in prompt


def test_socrates_prompt_forbids_verdict_and_requires_questions_per_side():
    prompt = load_philosopher_prompt("socrates")
    lowered = prompt.lower()
    assert "verdict" in lowered
    assert "weakest premise" in lowered
    assert "question" in lowered
    assert "2" in prompt and "3" in prompt
    assert "per speaker" in lowered or "per side" in lowered
    assert "node_ids" in prompt


def test_aristotle_fixture_gives_verdict_with_syllogism_and_fallacy():
    result = _load_result()
    known = {node.id for node in result.nodes}
    reply = PhilosopherReply.model_validate(_load_canned("aristotle_reply.json"))
    assert reply.philosopher == "aristotle"
    assert "S1" in reply.summary
    assert "argued better" in reply.summary.lower()
    assert len(reply.points) >= 3
    for point in reply.points:
        assert point.node_ids
        assert set(point.node_ids) <= known
    lowered = [point.text.lower() for point in reply.points]
    assert any("syllogism" in text or "syllogistic" in text for text in lowered)
    fallacy_words = (
        "fallac",
        "straw man",
        "ad hominem",
        "hasty",
        "false dilemma",
        "begging",
        "slippery",
        "appeal to",
    )
    assert any(any(word in text for word in fallacy_words) for text in lowered)
    cited = {nid for point in reply.points for nid in point.node_ids}
    speakers = {node.speaker for node in result.nodes if node.id in cited}
    assert {"S1", "S2"} <= speakers


def test_socrates_fixture_asks_questions_with_no_verdict():
    result = _load_result()
    known = {node.id for node in result.nodes}
    speaker_of = {node.id: node.speaker for node in result.nodes}
    reply = PhilosopherReply.model_validate(_load_canned("socrates_reply.json"))
    assert reply.philosopher == "socrates"
    assert 4 <= len(reply.points) <= 6
    whole = (
        reply.summary + "\n" + "\n".join(point.text for point in reply.points)
    ).lower()
    for banned in BANNED_VERDICT_WORDS:
        assert banned not in whole
    counts = {"S1": 0, "S2": 0}
    for point in reply.points:
        assert point.node_ids
        assert set(point.node_ids) <= known
        assert "?" in point.text
        sides = {speaker_of[nid] for nid in point.node_ids}
        assert len(sides) == 1
        counts[next(iter(sides))] += 1
    assert 2 <= counts["S1"] <= 3
    assert 2 <= counts["S2"] <= 3


def test_ask_philosopher_accepts_aristotle_fixture(monkeypatch):
    result = _load_result()
    canned = _load_canned("aristotle_reply.json")
    monkeypatch.setattr(
        pmod, "chat_json_validated", _fake_validated_factory(canned)
    )
    reply = ask_philosopher("aristotle", result)
    assert reply.philosopher == "aristotle"
    assert "argued better" in reply.summary.lower()


def test_ask_philosopher_accepts_socrates_fixture(monkeypatch):
    result = _load_result()
    canned = _load_canned("socrates_reply.json")
    monkeypatch.setattr(
        pmod, "chat_json_validated", _fake_validated_factory(canned)
    )
    reply = ask_philosopher("socrates", result)
    assert reply.philosopher == "socrates"
    assert 4 <= len(reply.points) <= 6
    assert all("?" in point.text for point in reply.points)


def test_socrates_endpoint_returns_questions(monkeypatch):
    canned = _load_canned("socrates_reply.json")
    monkeypatch.setattr(
        pmod, "chat_json_validated", _fake_validated_factory(canned)
    )
    body = {
        "philosopher": "socrates",
        "result": json.loads(
            (FIXTURES / "sample_debate.json").read_text(encoding="utf-8")
        ),
    }
    response = client.post("/api/philosopher", json=body)
    assert response.status_code == 200, response.text
    reply = PhilosopherReply.model_validate(response.json())
    assert len(reply.points) == 5
    assert all("?" in point.text for point in reply.points)
