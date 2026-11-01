"""Live smoke test: one short transcript through the full pipeline.

Runs ONLY when ``RUN_LIVE=1`` (real Meta Model API calls, costs a few
cents); ``scripts/check.ps1`` ignores ``tests/live`` and unsets ``RUN_LIVE``,
so this never runs in the offline gate. Emre runs it manually from
``backend/`` with ``backend/.env`` filled in::

    $env:RUN_LIVE = "1"; py -3.12 -m pytest tests/live -q

The transcript is pasted text (``POST /api/transcript``, no model call),
then ``POST /api/analyze`` (Analyst -> deterministic verifier ->
FallacyHunter -> semantic verifier) and ``POST /api/philosopher``
(Aristotle). Assertions stay loose on purpose: live model wording is
unpredictable, so this checks the contract shape, not exact content.
"""

import os
from pathlib import Path

import pytest
from dotenv import load_dotenv
from fastapi.testclient import TestClient

BACKEND_DIR = Path(__file__).resolve().parents[2]
load_dotenv(BACKEND_DIR / ".env")

RUN_LIVE = os.environ.get("RUN_LIVE") == "1"

pytestmark = pytest.mark.skipif(
    not RUN_LIVE,
    reason="Live Meta API test; run with RUN_LIVE=1 and backend/.env filled in.",
)

# Short non-political debate (5 turns, ~45s) kept tiny to minimise cost.
SMOKE_TRANSCRIPT = """\
[00:00] Speaker 1: Our school cafeteria should switch to reusable trays. Disposable trays fill three bins every lunch.
[00:10] Speaker 2: Reusable trays need washing, and our kitchen staff is already stretched thin.
[00:20] Speaker 1: A study of nearby schools showed washing takes ten minutes a day with the new racks.
[00:30] Speaker 2: So you are saying we should never use anything disposable ever again? That is absurd.
[00:38] Speaker 1: No, I said trays, not everything. Let us trial reusables for one month and compare costs.
"""


def test_live_smoke_full_pipeline(monkeypatch, tmp_path):
    from app import analyze as anmod
    from app.main import app
    from app.schemas import DebateResult

    if not os.environ.get("META_API_KEY", "").strip():
        pytest.skip("META_API_KEY is not set; fill in backend/.env first.")

    # Keep the live run from overwriting the demo file (task 19).
    monkeypatch.setattr(anmod, "LAST_RESULT_PATH", tmp_path / "last_result.json")

    client = TestClient(app)

    transcript = client.post("/api/transcript", json={"text": SMOKE_TRANSCRIPT})
    assert transcript.status_code == 200, transcript.text
    assert len(transcript.json()["segments"]) == 5

    analyzed = client.post("/api/analyze", json=transcript.json())
    assert analyzed.status_code == 200, analyzed.text
    result = DebateResult.model_validate(analyzed.json())
    assert result.nodes, "live analyst returned no argument nodes"
    known_ids = {node.id for node in result.nodes}
    assert len(known_ids) == len(result.nodes)
    for edge in result.edges:
        assert edge.source in known_ids and edge.target in known_ids
    for fallacy in result.fallacies:
        assert fallacy.node_id in known_ids

    judged = client.post(
        "/api/philosopher",
        json={"philosopher": "aristotle", "result": analyzed.json()},
    )
    assert judged.status_code == 200, judged.text
    reply = judged.json()
    assert reply["points"], "live philosopher returned no points"
    for point in reply["points"]:
        assert point["node_ids"]
        assert set(point["node_ids"]) <= known_ids

    print(
        f"live smoke ok: {len(result.nodes)} nodes, "
        f"{len(result.edges)} edges, "
        f"{len(result.fallacies)} fallacies, "
        f"{len(reply['points'])} philosopher points"
    )
