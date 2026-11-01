"""Analyst agent: transcript segments -> argument-graph nodes + edges (task 7).

The system prompt is ``app/prompts/analyst.md``; the transcript is rendered as
``[seg_id] speaker-id (Speaker label) (start-end): text`` lines. The Meta text model is
called through ``app.meta_client.chat_json_validated`` (structured output,
retried once on invalid JSON). The model returns node/edge drafts; this module
stamps ``verified=True`` on every node — the deterministic verifier (task 8)
and the semantic verifier (task 10) own downgrading failures to False.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import BaseModel

from app.meta_client import chat_json_validated
from app.schemas import Edge, Node, NodeType, Segment, Speaker

PROMPT_PATH = Path(__file__).resolve().parent / "prompts" / "analyst.md"
SCHEMA_NAME = "analyst_graph"


class AnalystNodeDraft(BaseModel):
    """One node as the model returns it (no ``verified`` flag; see module doc)."""

    id: str
    type: NodeType
    speaker: str
    text: str
    quote: str
    start: float
    segment_ids: list[str]


class AnalystReply(BaseModel):
    """Structured-output shape for the analyst chat call."""

    nodes: list[AnalystNodeDraft]
    edges: list[Edge]


def load_analyst_prompt() -> str:
    """Read the analyst system prompt from ``app/prompts/analyst.md``."""
    return PROMPT_PATH.read_text(encoding="utf-8")


def format_transcript(speakers: list[Speaker], segments: list[Segment]) -> str:
    """Render segments as ``[seg_id] speaker-id (label) (start-end): text`` lines.

    Both the speaker id (``S1``) and the human label are included so the
    model can attribute moves by id while still reading a friendly name.
    """
    labels = {speaker.id: speaker.label for speaker in speakers}
    lines = [
        f"[{seg.id}] {seg.speaker} ({labels.get(seg.speaker, seg.speaker)})"
        f" ({seg.start}s-{seg.end}s): {seg.text}"
        for seg in segments
    ]
    return (
        "Transcript segments (times in seconds):\n"
        + "\n".join(lines)
        + "\nExtract the argument graph now."
    )


def build_analyst_messages(
    speakers: list[Speaker], segments: list[Segment]
) -> list[dict[str, Any]]:
    """System prompt + rendered transcript for the analyst chat call."""
    return [
        {"role": "system", "content": load_analyst_prompt()},
        {"role": "user", "content": format_transcript(speakers, segments)},
    ]


def analyze_transcript(
    speakers: list[Speaker],
    segments: list[Segment],
    *,
    model: str | None = None,
    client: Any | None = None,
) -> tuple[list[Node], list[Edge]]:
    """Run the analyst agent; returns contract ``(nodes, edges)``.

    ``model`` defaults to ``META_TEXT_MODEL``. Pass ``client`` only in tests.
    Raises ValueError when there are no segments; MetaClientError from
    ``meta_client`` propagates unchanged after its one retry.
    """
    if not segments:
        raise ValueError("No transcript segments to analyze.")
    messages = build_analyst_messages(speakers, segments)
    reply = chat_json_validated(
        messages,
        response_model=AnalystReply,
        schema_name=SCHEMA_NAME,
        model=model,
        client=client,
    )
    nodes = [Node(**draft.model_dump(), verified=True) for draft in reply.nodes]
    # Graph integrity at the boundary: drop edges that point at unknown
    # nodes or at themselves, so the API graph and the UI graph cannot
    # silently diverge (the UI drops the same edges when rendering).
    known = {node.id for node in nodes}
    edges = [
        edge
        for edge in reply.edges
        if edge.source in known and edge.target in known and edge.source != edge.target
    ]
    return nodes, edges
