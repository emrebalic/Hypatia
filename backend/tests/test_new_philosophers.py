"""Offline tests for the added judges: Kant, Marcus Aurelius, Epicurus.

The Meta text model is faked by patching app.philosopher.chat_json_validated;
canned replies live in fixtures/kant_reply.json,
fixtures/marcus-aurelius_reply.json and fixtures/epicurus_reply.json, and
the debate input in fixtures/sample_debate.json. No network is used.

Each new judge applies its own method (Kant: maxim + universalisability +
humanity; Marcus Aurelius: dichotomy of control + virtues; Epicurus:
desires + needless fear), states its "Will not" rules, and grounds every
point in real node ids covering both speakers.
"""

import copy
import json
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app import philosopher as pmod
from app.main import app
from app.philosopher import PhilosopherReply, ask_philosopher, load_philosopher_prompt
from app.schemas import DebateResult

client = TestClient(app)

FIXTURES = Path(__file__).resolve().parents[2] / "fixtures"

NEW_JUDGES = ("kant", "marcus-aurelius", "epicurus")

METHOD_WORDS: dict[str, tuple[str, ...]] = {
    "kant": ("maxim", "universal", "merely as a means"),
    "marcus-aurelius": ("control", "virtue"),
    "epicurus": ("desire", "fear"),
}


def _load_result() -> DebateResult:
    return DebateResult.model_validate(
        json.loads((FIXTURES / "sample_debate.json").read_text(encoding="utf-8"))
    )


def _load_canned(philosopher: str) -> dict[str, Any]:
    return copy.deepcopy(
        json.loads(
            (FIXTURES / f"{philosopher}_reply.json").read_text(encoding="utf-8")
        )
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


@pytest.mark.parametrize("philosopher", NEW_JUDGES)
def test_new_prompt_teaches_its_method(philosopher: str):
    prompt = load_philosopher_prompt(philosopher)
    lowered = prompt.lower()
    for word in METHOD_WORDS[philosopher]:
        assert word in lowered, f"{philosopher} prompt misses {word!r}"
    assert f'"philosopher": "{philosopher}"' in prompt
    assert "node_ids" in prompt
    assert "cover both sides" in lowered


@pytest.mark.parametrize("philosopher", NEW_JUDGES)
def test_new_prompt_states_will_not_rules(philosopher: str):
    prompt = load_philosopher_prompt(philosopher)
    lowered = prompt.lower()
    assert "will not" in lowered
    assert "paraphrase" in lowered
    assert "do not invent" in lowered


def test_kant_prompt_names_both_formulae():
    lowered = load_philosopher_prompt("kant").lower()
    assert "categorical imperative" in lowered
    assert "humanity formula" in lowered
    assert "consequences" in lowered  # in the Will-not list


def test_marcus_prompt_names_the_four_virtues():
    lowered = load_philosopher_prompt("marcus-aurelius").lower()
    for virtue in ("wisdom", "courage", "justice", "temperance"):
        assert virtue in lowered
    assert "dichotomy of control" in lowered


def test_epicurus_prompt_forbids_medical_advice():
    lowered = load_philosopher_prompt("epicurus").lower()
    assert "medical" in lowered
    assert "natural and necessary" in lowered
    assert "ataraxia" in lowered


@pytest.mark.parametrize("philosopher", NEW_JUDGES)
def test_new_fixture_covers_both_sides_with_real_nodes(philosopher: str):
    result = _load_result()
    known = {node.id for node in result.nodes}
    speaker_of = {node.id: node.speaker for node in result.nodes}
    reply = PhilosopherReply.model_validate(_load_canned(philosopher))
    assert reply.philosopher == philosopher
    assert reply.summary.strip()
    assert len(reply.points) >= 3
    cited: set[str] = set()
    for point in reply.points:
        assert point.node_ids
        assert set(point.node_ids) <= known
        cited.update(point.node_ids)
    speakers = {speaker_of[nid] for nid in cited}
    assert {"S1", "S2"} <= speakers
    combined = "\n".join(point.text for point in reply.points).lower()
    for word in METHOD_WORDS[philosopher]:
        assert word.split()[0] in combined or word in combined


@pytest.mark.parametrize("philosopher", NEW_JUDGES)
def test_ask_philosopher_accepts_new_judges(monkeypatch, philosopher: str):
    result = _load_result()
    canned = _load_canned(philosopher)
    monkeypatch.setattr(
        pmod, "chat_json_validated", _fake_validated_factory(canned)
    )
    reply = ask_philosopher(philosopher, result)  # type: ignore[arg-type]
    assert reply.philosopher == philosopher
    assert len(reply.points) >= 3


@pytest.mark.parametrize("philosopher", NEW_JUDGES)
def test_new_judge_endpoint_returns_judgement(monkeypatch, philosopher: str):
    canned = _load_canned(philosopher)
    monkeypatch.setattr(
        pmod, "chat_json_validated", _fake_validated_factory(canned)
    )
    body = {
        "philosopher": philosopher,
        "result": json.loads(
            (FIXTURES / "sample_debate.json").read_text(encoding="utf-8")
        ),
    }
    response = client.post("/api/philosopher", json=body)
    assert response.status_code == 200, response.text
    reply = PhilosopherReply.model_validate(response.json())
    assert reply.philosopher == philosopher
