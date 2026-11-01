"""Offline tests for the philosopher judges (app.philosopher, task 16).

The Meta text model is faked by patching app.philosopher.chat_json_validated;
the canned reply lives in fixtures/philosopher_reply.json and the debate
input in fixtures/sample_debate.json. No network is used. Every point of a
reply must reference at least one real node id; replies breaking that
contract are rejected.
"""

import copy
import json
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app import philosopher as pmod
from app.main import app
from app.meta_client import MetaClientError
from app.philosopher import (
    PhilosopherReply,
    ask_philosopher,
    build_philosopher_messages,
    load_philosopher_prompt,
)
from app.schemas import DebateResult

client = TestClient(app)

FIXTURES = Path(__file__).resolve().parents[2] / "fixtures"


def _load_result() -> dict[str, Any]:
    return copy.deepcopy(
        json.loads((FIXTURES / "sample_debate.json").read_text(encoding="utf-8"))
    )


def _canned_reply() -> dict[str, Any]:
    return copy.deepcopy(
        json.loads((FIXTURES / "philosopher_reply.json").read_text(encoding="utf-8"))
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


def _request_body(philosopher: str = "aristotle") -> dict[str, Any]:
    body = {"philosopher": philosopher, "result": _load_result()}
    return body


def test_ask_returns_checked_reply(monkeypatch):
    result = DebateResult.model_validate(_load_result())
    seen: dict[str, Any] = {}
    monkeypatch.setattr(
        pmod, "chat_json_validated", _fake_validated_factory(_canned_reply(), seen)
    )
    reply = ask_philosopher("aristotle", result)
    assert isinstance(reply, PhilosopherReply)
    assert reply.philosopher == "aristotle"
    assert reply.summary.strip()
    assert len(reply.points) == 3
    known = {node.id for node in result.nodes}
    for point in reply.points:
        assert point.node_ids
        assert set(point.node_ids) <= known
    assert seen["response_model"] is PhilosopherReply
    assert seen["schema_name"] == pmod.SCHEMA_NAME


@pytest.mark.parametrize(
    "philosopher",
    ["aristotle", "socrates", "hypatia", "kant", "marcus-aurelius", "epicurus"],
)
def test_each_philosopher_uses_its_prompt_file(monkeypatch, philosopher):
    result = DebateResult.model_validate(_load_result())
    canned = _canned_reply()
    canned["philosopher"] = philosopher
    seen: dict[str, Any] = {}
    monkeypatch.setattr(
        pmod, "chat_json_validated", _fake_validated_factory(canned, seen)
    )
    reply = ask_philosopher(philosopher, result)  # type: ignore[arg-type]
    assert reply.philosopher == philosopher
    messages = seen["messages"]
    assert [message["role"] for message in messages] == ["system", "user"]
    assert messages[0]["content"] == load_philosopher_prompt(philosopher)
    user_text = messages[1]["content"]
    for node in result.nodes:
        assert node.id in user_text
    assert "n1" in user_text


def test_follow_up_message_reaches_model(monkeypatch):
    result = DebateResult.model_validate(_load_result())
    seen: dict[str, Any] = {}
    monkeypatch.setattr(
        pmod, "chat_json_validated", _fake_validated_factory(_canned_reply(), seen)
    )
    ask_philosopher("socrates", result, "What about the junior onboarding point?")
    assert "What about the junior onboarding point?" in seen["messages"][1]["content"]


def test_point_without_node_ids_is_rejected(monkeypatch):
    result = DebateResult.model_validate(_load_result())
    canned = _canned_reply()
    canned["points"][0]["node_ids"] = []
    monkeypatch.setattr(
        pmod, "chat_json_validated", _fake_validated_factory(canned, {})
    )
    with pytest.raises(MetaClientError):
        ask_philosopher("aristotle", result)


def test_unknown_node_id_is_rejected(monkeypatch):
    result = DebateResult.model_validate(_load_result())
    canned = _canned_reply()
    canned["points"][1]["node_ids"] = ["n999"]
    monkeypatch.setattr(
        pmod, "chat_json_validated", _fake_validated_factory(canned, {})
    )
    with pytest.raises(MetaClientError):
        ask_philosopher("aristotle", result)


def test_empty_points_are_rejected(monkeypatch):
    result = DebateResult.model_validate(_load_result())
    canned = _canned_reply()
    canned["points"] = []
    monkeypatch.setattr(
        pmod, "chat_json_validated", _fake_validated_factory(canned, {})
    )
    with pytest.raises(MetaClientError):
        ask_philosopher("aristotle", result)


def test_ask_rejects_empty_nodes(monkeypatch):
    data = _load_result()
    data["nodes"] = []
    result = DebateResult.model_validate(data)
    called = {"count": 0}

    def refuse(*args: Any, **kwargs: Any) -> Any:
        called["count"] += 1
        raise AssertionError("model must not be called without nodes")

    monkeypatch.setattr(pmod, "chat_json_validated", refuse)
    with pytest.raises(ValueError):
        ask_philosopher("aristotle", result)
    assert called["count"] == 0


def test_ask_propagates_model_error(monkeypatch):
    result = DebateResult.model_validate(_load_result())

    def fail(*args: Any, **kwargs: Any) -> Any:
        raise MetaClientError("chat model returned invalid JSON twice")

    monkeypatch.setattr(pmod, "chat_json_validated", fail)
    with pytest.raises(MetaClientError):
        ask_philosopher("aristotle", result)


def test_endpoint_returns_judgement(monkeypatch):
    seen: dict[str, Any] = {}
    monkeypatch.setattr(
        pmod, "chat_json_validated", _fake_validated_factory(_canned_reply(), seen)
    )
    response = client.post("/api/philosopher", json=_request_body())
    assert response.status_code == 200, response.text
    body = response.json()
    reply = PhilosopherReply.model_validate(body)
    assert reply.philosopher == "aristotle"
    assert len(reply.points) == 3
    assert all(point["node_ids"] for point in body["points"])


def test_endpoint_bad_point_is_502(monkeypatch):
    canned = _canned_reply()
    canned["points"][0]["node_ids"] = []
    monkeypatch.setattr(
        pmod, "chat_json_validated", _fake_validated_factory(canned, {})
    )
    response = client.post("/api/philosopher", json=_request_body())
    assert response.status_code == 502, response.text


def test_endpoint_empty_nodes_is_400(monkeypatch):
    called = {"count": 0}

    def refuse(*args: Any, **kwargs: Any) -> Any:
        called["count"] += 1
        raise AssertionError("model must not be called without nodes")

    monkeypatch.setattr(pmod, "chat_json_validated", refuse)
    body = _request_body()
    body["result"]["nodes"] = []
    response = client.post("/api/philosopher", json=body)
    assert response.status_code == 400, response.text
    assert called["count"] == 0


def test_endpoint_unknown_philosopher_is_422():
    response = client.post("/api/philosopher", json=_request_body("plato"))
    assert response.status_code == 422, response.text


def test_endpoint_model_error_is_502(monkeypatch):
    def fail(*args: Any, **kwargs: Any) -> Any:
        raise MetaClientError("chat model returned invalid JSON twice")

    monkeypatch.setattr(pmod, "chat_json_validated", fail)
    response = client.post("/api/philosopher", json=_request_body())
    assert response.status_code == 502, response.text


def test_unverified_items_are_flagged_for_the_judge():
    from app.fallacy import format_nodes
    from app.philosopher import format_fallacies

    result = DebateResult.model_validate(_load_result())
    broken = result.model_copy(
        update={
            "nodes": [
                node.model_copy(update={"verified": False})
                if node.id == "n5"
                else node
                for node in result.nodes
            ],
            "fallacies": [
                fallacy.model_copy(update={"verified": False})
                if fallacy.id == "f1"
                else fallacy
                for fallacy in result.fallacies
            ],
        }
    )
    node_lines = format_nodes(broken.nodes)
    assert "[n5]" in node_lines and "UNVERIFIED" in node_lines.split("[n5]")[1].splitlines()[0]
    fallacy_lines = format_fallacies(broken)
    assert "UNVERIFIED" in fallacy_lines.split("[f1]")[1].splitlines()[0]
    # Verified neighbours are not flagged.
    assert "UNVERIFIED" not in node_lines.split("[n1]")[1].splitlines()[0]


def test_canned_fixture_references_real_nodes():
    """The canned reply is judge-quality: every point cites real node ids."""
    data = json.loads((FIXTURES / "sample_debate.json").read_text(encoding="utf-8"))
    node_ids = {node["id"] for node in data["nodes"]}
    reply = PhilosopherReply.model_validate(_canned_reply())
    assert reply.points
    for point in reply.points:
        assert point.node_ids
        assert set(point.node_ids) <= node_ids
    for philosopher in (
        "aristotle",
        "socrates",
        "hypatia",
        "kant",
        "marcus-aurelius",
        "epicurus",
    ):
        assert load_philosopher_prompt(philosopher).strip()
        assert "node_ids" in load_philosopher_prompt(philosopher)
    assert build_philosopher_messages(
        "aristotle", DebateResult.model_validate(data)
    )[0]["content"].strip()
