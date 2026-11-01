"""Offline tests for demo mode (app.demo, TASKS.md task 19).

GET /api/demo loads ``backend/data/last_result.json`` with no model calls.
The saved file is redirected to tmp_path so tests never touch the real
``backend/data/`` file.
"""

import copy
import json
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from app import analyst as amod
from app import demo as dmod
from app import fallacy as fmod
from app import semantic_verifier as smod
from app.main import app
from app.schemas import DebateResult

client = TestClient(app)

FIXTURES = Path(__file__).resolve().parents[2] / "fixtures"


def _sample_result() -> dict[str, Any]:
    return copy.deepcopy(
        json.loads((FIXTURES / "sample_debate.json").read_text(encoding="utf-8"))
    )


def test_demo_returns_saved_result(monkeypatch, tmp_path):
    saved = tmp_path / "last_result.json"
    saved.write_text(json.dumps(_sample_result()), encoding="utf-8")
    monkeypatch.setattr(dmod, "LAST_RESULT_PATH", saved)
    response = client.get("/api/demo")
    assert response.status_code == 200, response.text
    result = DebateResult.model_validate(response.json())
    assert len(result.nodes) == 9
    assert len(result.edges) == 8
    assert len(result.fallacies) == 3
    assert [s.id for s in result.speakers] == ["S1", "S2"]
    assert response.json() == _sample_result()


def test_demo_makes_no_model_calls(monkeypatch, tmp_path):
    saved = tmp_path / "last_result.json"
    saved.write_text(json.dumps(_sample_result()), encoding="utf-8")
    monkeypatch.setattr(dmod, "LAST_RESULT_PATH", saved)

    def refuse(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError("demo mode must not call the model")

    monkeypatch.setattr(amod, "chat_json_validated", refuse)
    monkeypatch.setattr(fmod, "chat_json_validated", refuse)
    monkeypatch.setattr(smod, "chat_json_validated", refuse)
    response = client.get("/api/demo")
    assert response.status_code == 200, response.text


def test_demo_missing_file_is_404(monkeypatch, tmp_path):
    monkeypatch.setattr(dmod, "LAST_RESULT_PATH", tmp_path / "missing.json")
    response = client.get("/api/demo")
    assert response.status_code == 404, response.text
    assert "No saved demo result" in response.json()["detail"]


def test_demo_invalid_json_is_500(monkeypatch, tmp_path):
    saved = tmp_path / "last_result.json"
    saved.write_text("{not valid json", encoding="utf-8")
    monkeypatch.setattr(dmod, "LAST_RESULT_PATH", saved)
    response = client.get("/api/demo")
    assert response.status_code == 500, response.text


def test_demo_wrong_shape_is_500(monkeypatch, tmp_path):
    saved = tmp_path / "last_result.json"
    saved.write_text(json.dumps({"nodes": []}), encoding="utf-8")
    monkeypatch.setattr(dmod, "LAST_RESULT_PATH", saved)
    response = client.get("/api/demo")
    assert response.status_code == 500, response.text


def test_load_demo_result_round_trip(monkeypatch, tmp_path):
    saved = tmp_path / "nested" / "last_result.json"
    saved.parent.mkdir(parents=True)
    data = _sample_result()
    saved.write_text(json.dumps(data), encoding="utf-8")
    assert dmod.load_demo_result(saved) == DebateResult.model_validate(data)
