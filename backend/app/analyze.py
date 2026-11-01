"""Full analysis pipeline endpoint (TASKS.md task 11).

POST /api/analyze runs Analyst -> FallacyHunter -> Verifiers and returns
the full contract JSON (``app.schemas.DebateResult``). The result is also
saved to ``backend/data/last_result.json`` for fast demo reloads (task 19
loads that file with no API calls).

Pipeline order:
1. Analyst (``app.analyst.analyze_transcript``) maps segments to nodes+edges.
2. Deterministic verifier (``app.verifier.verify_nodes``) checks quotes
   verbatim in transcript and timestamps inside segments.
3. FallacyHunter (``app.fallacy.hunt_fallacies``) and the node semantic
   verifier run concurrently; both only need the deterministically
   verified nodes.
4. Fallacy semantic verifier (``app.semantic_verifier``) asks the model
   whether each still-verified quote supports its label.

Failure policy: an Analyst failure is fatal (no graph to show). A
FallacyHunter or semantic-verifier failure degrades gracefully — the
deterministically verified graph is returned (with an empty fallacy list
when the hunter failed) instead of failing the whole analysis.

All network calls go through ``app.meta_client`` (via the agent modules),
so tests can fake the model offline.
"""

from __future__ import annotations

import logging
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app import analyst as analyst_mod
from app import fallacy as fallacy_mod
from app import semantic_verifier as semantic_mod
from app import verifier as verifier_mod
from app.meta_client import MetaClientError
from app.schemas import DebateResult, Segment, Speaker

router = APIRouter()
logger = logging.getLogger(__name__)

LAST_RESULT_PATH = Path(__file__).resolve().parents[1] / "data" / "last_result.json"


class AnalyzeRequest(BaseModel):
    """Transcript input: speakers + segments (as returned by /api/transcribe)."""

    speakers: list[Speaker]
    segments: list[Segment]


def save_result(result: DebateResult, path: Path = LAST_RESULT_PATH) -> Path:
    """Write ``result`` as JSON to ``path`` atomically (temp file + rename).

    A concurrent reader (GET /api/demo) must never observe a torn file:
    the payload is written beside the target and renamed over it.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    # Unique temp name: concurrent analyses must not share one temp file.
    tmp = path.with_name(f"{path.name}.{uuid.uuid4().hex[:12]}.tmp")
    try:
        tmp.write_text(result.model_dump_json(indent=2), encoding="utf-8")
        tmp.replace(path)
    finally:
        tmp.unlink(missing_ok=True)
    return path


def run_analysis(
    speakers: list[Speaker],
    segments: list[Segment],
    *,
    save_path: Path | None = None,
) -> DebateResult:
    """Run the full pipeline and persist the result.

    Raises ValueError when there are no segments. An Analyst
    MetaClientError propagates unchanged (fatal: no graph). FallacyHunter
    and semantic-verifier MetaClientErrors degrade gracefully to the
    deterministically verified graph (see module docstring).
    """
    if not segments:
        raise ValueError("No transcript segments to analyze.")
    nodes, edges = analyst_mod.analyze_transcript(speakers, segments)
    nodes = verifier_mod.verify_nodes(nodes, segments)
    # Unknown speakers cannot be grounded in the transcript either.
    known_speakers = {speaker.id for speaker in speakers}
    nodes = [
        node
        if node.speaker in known_speakers
        else node.model_copy(update={"verified": False})
        for node in nodes
    ]
    # Fallacy hunting and node semantic verification are independent: both
    # consume the deterministically verified nodes, so run them together.
    with ThreadPoolExecutor(max_workers=2) as pool:
        fallacy_future = pool.submit(
            fallacy_mod.hunt_fallacies, speakers, segments, nodes
        )
        node_future = pool.submit(
            semantic_mod.verify_nodes_semantic, nodes, segments, speakers
        )
        try:
            fallacies = fallacy_future.result()
        except MetaClientError as exc:
            logger.warning("FallacyHunter failed, returning no fallacies: %s", exc)
            fallacies = []
        try:
            nodes = node_future.result()
        except MetaClientError as exc:
            logger.warning(
                "Node semantic verifier failed, keeping deterministic flags: %s", exc
            )
    try:
        fallacies = semantic_mod.verify_fallacies_semantic(
            fallacies, segments, nodes, speakers
        )
    except MetaClientError as exc:
        logger.warning(
            "Fallacy semantic verifier failed, keeping deterministic flags: %s", exc
        )
    result = DebateResult(
        speakers=speakers,
        segments=segments,
        nodes=nodes,
        edges=edges,
        fallacies=fallacies,
    )
    save_result(result, save_path or LAST_RESULT_PATH)
    return result


@router.post("/api/analyze", response_model=DebateResult)
def post_analyze(body: AnalyzeRequest) -> DebateResult:
    """Analyze a transcript: Analyst -> FallacyHunter -> Verifiers."""
    try:
        return run_analysis(body.speakers, body.segments)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except MetaClientError as exc:
        raise HTTPException(
            status_code=502, detail=f"Analysis failed: {exc}"
        ) from exc
    except OSError as exc:
        raise HTTPException(
            status_code=500, detail=f"Could not save analysis result: {exc}"
        ) from exc
