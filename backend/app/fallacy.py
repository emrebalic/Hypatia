"""FallacyHunter agent: transcript + argument graph -> fallacy report (task 9).

The system prompt is ``app/prompts/fallacy.md``; the transcript segments and
the analyst's nodes are rendered as text lines. The Meta text model is called
through ``app.meta_client.chat_json_validated`` (structured output, retried
once on invalid JSON). The model returns fallacy drafts; this module stamps
``verified=True`` on each one and then runs them through the deterministic
verifier (task 8: quote verbatim in transcript, start inside the linked
node's segments), which downgrades failures to ``verified=False``.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import BaseModel

from app.analyst import format_transcript
from app.meta_client import chat_json_validated
from app.schemas import Fallacy, Node, Segment, Speaker
from app.verifier import ground_fallacies, verify_fallacies

PROMPT_PATH = Path(__file__).resolve().parent / "prompts" / "fallacy.md"
SCHEMA_NAME = "fallacy_report"


class FallacyDraft(BaseModel):
    """One fallacy as the model returns it (no ``verified`` flag; see module doc)."""

    id: str
    node_id: str
    name: str
    explanation: str
    quote: str
    start: float


class FallacyReply(BaseModel):
    """Structured-output shape for the FallacyHunter chat call."""

    fallacies: list[FallacyDraft]


def load_fallacy_prompt() -> str:
    """Read the FallacyHunter system prompt from ``app/prompts/fallacy.md``."""
    return PROMPT_PATH.read_text(encoding="utf-8")


def format_nodes(nodes: list[Node]) -> str:
    """Render nodes as ``[node-id] (type, speaker, segments, start, flag): ...``.

    The verification flag travels with the node: an UNVERIFIED node failed
    the deterministic/semantic checks and must not be treated as
    established fact by the receiving agent.
    """
    lines = [
        f"[{node.id}] ({node.type}, {node.speaker},"
        f" {','.join(node.segment_ids)}, {node.start}s,"
        f" {'verified' if node.verified else 'UNVERIFIED — failed verification'}):"
        f" {node.text} | quote: {node.quote}"
        for node in nodes
    ]
    return "Argument nodes:\n" + "\n".join(lines)


def build_fallacy_messages(
    speakers: list[Speaker], segments: list[Segment], nodes: list[Node]
) -> list[dict[str, Any]]:
    """System prompt + rendered transcript and nodes for the chat call."""
    return [
        {"role": "system", "content": load_fallacy_prompt()},
        {
            "role": "user",
            "content": format_transcript(speakers, segments)
            + "\n"
            + format_nodes(nodes)
            + "\nFlag the fallacies now.",
        },
    ]


def hunt_fallacies(
    speakers: list[Speaker],
    segments: list[Segment],
    nodes: list[Node],
    *,
    model: str | None = None,
    client: Any | None = None,
) -> list[Fallacy]:
    """Run the FallacyHunter agent; returns contract fallacies.

    ``model`` defaults to ``META_TEXT_MODEL``. Pass ``client`` only in tests.
    Raises ValueError when there are no segments. With no nodes there is
    nothing to link a fallacy to, so an empty list is returned without calling
    the model. Every returned fallacy has passed through ``verify_fallacies``,
    so invented quotes and out-of-range timestamps come back ``verified=False``.
    MetaClientError from ``meta_client`` propagates unchanged after its retry.
    """
    if not segments:
        raise ValueError("No transcript segments to hunt fallacies in.")
    if not nodes:
        return []
    messages = build_fallacy_messages(speakers, segments, nodes)
    reply = chat_json_validated(
        messages,
        response_model=FallacyReply,
        schema_name=SCHEMA_NAME,
        model=model,
        client=client,
    )
    stamped = [Fallacy(**draft.model_dump(), verified=True) for draft in reply.fallacies]
    return verify_fallacies(ground_fallacies(stamped, segments, nodes), segments, nodes)
