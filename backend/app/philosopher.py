"""Philosopher judges: all six Learn-panel philosophers (task 16, expanded).

POST /api/philosopher takes a finished ``DebateResult`` plus the chosen
philosopher (and an optional one-shot ``user_message`` follow-up) and asks
the Meta text model for a judgement. The system prompt comes from
``app/prompts/<philosopher>.md`` — Aristotle (syllogism + verdict),
Socrates (elenchus, no verdict), Hypatia (proof check, no winner), Kant
(universalisability), Marcus Aurelius (Stoic control + virtues) and
Epicurus (calm / needless-fear check). All network calls go through
``app.meta_client.chat_json_validated`` (structured output, retried once on
invalid JSON), so tests can fake the model offline.

Contract: the reply is a summary plus a list of points, and every point
must reference at least one real node id from the input ``result``. Replies
with no points, with a point missing node ids, or with an unknown node id
are rejected as model failures (MetaClientError -> HTTP 502).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.analyst import format_transcript
from app.fallacy import format_nodes
from app.meta_client import MetaClientError, chat_json_validated
from app.schemas import DebateResult

router = APIRouter()

PhilosopherName = Literal[
    "aristotle", "socrates", "hypatia", "kant", "marcus-aurelius", "epicurus"
]

PROMPT_DIR = Path(__file__).resolve().parent / "prompts"
PROMPT_FILES: dict[str, str] = {
    "aristotle": "aristotle.md",
    "socrates": "socrates.md",
    "hypatia": "hypatia.md",
    "kant": "kant.md",
    "marcus-aurelius": "marcus-aurelius.md",
    "epicurus": "epicurus.md",
}
SCHEMA_NAME = "philosopher_judgement"


class PhilosopherPoint(BaseModel):
    """One judgement step; always tied to argument nodes."""

    title: str = ""
    text: str
    node_ids: list[str]


class PhilosopherReply(BaseModel):
    """Structured-output shape for the philosopher chat call and the endpoint."""

    philosopher: PhilosopherName
    summary: str
    points: list[PhilosopherPoint]


class PhilosopherRequest(BaseModel):
    """POST /api/philosopher body: who judges, what they judge, follow-up?"""

    philosopher: PhilosopherName
    result: DebateResult
    user_message: str | None = None


def load_philosopher_prompt(philosopher: str) -> str:
    """Read the system prompt for ``philosopher`` from its prompt file."""
    try:
        filename = PROMPT_FILES[philosopher]
    except KeyError:
        raise ValueError(f"Unknown philosopher: {philosopher!r}.") from None
    return (PROMPT_DIR / filename).read_text(encoding="utf-8")


def format_edges(result: DebateResult) -> str:
    """Render edges as ``source -> target (relation)`` lines."""
    lines = [
        f"{edge.source} -> {edge.target} ({edge.relation})"
        for edge in result.edges
    ]
    return "Edges:\n" + ("\n".join(lines) if lines else "(none)")


def format_fallacies(result: DebateResult) -> str:
    """Render fallacies as ``[fallacy-id] (name, node): explanation`` lines."""
    lines = [
        f"[{fallacy.id}] ({fallacy.name}, node={fallacy.node_id}):"
        f" {fallacy.explanation}"
        for fallacy in result.fallacies
    ]
    return "Fallacies:\n" + ("\n".join(lines) if lines else "(none)")


def build_philosopher_messages(
    philosopher: PhilosopherName,
    result: DebateResult,
    user_message: str | None = None,
) -> list[dict[str, Any]]:
    """System prompt + rendered argument graph (+ optional follow-up)."""
    body = (
        format_transcript(result.speakers, result.segments)
        + "\n"
        + format_nodes(result.nodes)
        + "\n"
        + format_edges(result)
        + "\n"
        + format_fallacies(result)
    )
    if user_message and user_message.strip():
        body += f"\nFollow-up question from the user: {user_message.strip()}"
    else:
        body += "\nGive your judgement now."
    return [
        {"role": "system", "content": load_philosopher_prompt(philosopher)},
        {"role": "user", "content": body},
    ]


def check_point_node_ids(reply: PhilosopherReply, result: DebateResult) -> None:
    """Enforce the task-16 contract: every point references real node ids.

    Raises MetaClientError when the reply has no points, when any point
    lists no node ids, or when any listed id is not a node of ``result``.
    """
    known = {node.id for node in result.nodes}
    if not reply.points:
        raise MetaClientError("philosopher reply has no points")
    for index, point in enumerate(reply.points):
        if not point.node_ids:
            raise MetaClientError(
                f"philosopher point {index} references no node ids"
            )
        unknown = [nid for nid in point.node_ids if nid not in known]
        if unknown:
            raise MetaClientError(
                f"philosopher point {index} references unknown node ids: "
                + ", ".join(sorted(unknown))
            )


def ask_philosopher(
    philosopher: PhilosopherName,
    result: DebateResult,
    user_message: str | None = None,
    *,
    model: str | None = None,
    client: Any | None = None,
) -> PhilosopherReply:
    """Run one philosopher judgement; returns the checked reply.

    ``model`` defaults to ``META_TEXT_MODEL``. Pass ``client`` only in tests.
    Raises ValueError when the result has no nodes; MetaClientError from
    ``meta_client`` (or for a reply breaking the node-id contract)
    propagates unchanged after its retry.
    """
    if philosopher not in PROMPT_FILES:
        raise ValueError(f"Unknown philosopher: {philosopher!r}.")
    if not result.nodes:
        raise ValueError("No argument nodes to judge.")
    messages = build_philosopher_messages(philosopher, result, user_message)
    reply = chat_json_validated(
        messages,
        response_model=PhilosopherReply,
        schema_name=SCHEMA_NAME,
        model=model,
        client=client,
    )
    # Keep the reply consistent with the request even if the model echoed
    # a different name; the schema allows only the six valid names.
    reply = reply.model_copy(update={"philosopher": philosopher})
    check_point_node_ids(reply, result)
    return reply


@router.post("/api/philosopher", response_model=PhilosopherReply)
def post_philosopher(body: PhilosopherRequest) -> PhilosopherReply:
    """Judge an argument graph with the chosen philosopher's method."""
    try:
        return ask_philosopher(
            body.philosopher, body.result, body.user_message
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except MetaClientError as exc:
        raise HTTPException(
            status_code=502, detail=f"Philosopher failed: {exc}"
        ) from exc
