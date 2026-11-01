"""Semantic verifier agent: does the quote support the label? (task 10).

The deterministic verifier (task 8, ``app.verifier``) already enforced the
textual rules — every quote appears verbatim in the transcript and every
start falls inside its segment — downgrading failures to ``verified=False``.
This module handles what text matching cannot: for items still
``verified=True`` it asks the Meta text model whether the quote actually
supports its label, and downgrades ``supported=false`` items to
``verified=False``.

- Nodes: does the quote actually say what the node's paraphrase (``text``)
  claims, with a fitting ``type``?
- Fallacies: does the quote actually commit the named fallacy (``name``)
  for the given ``explanation``?

The system prompt is ``app/prompts/semantic_verifier.md``. All network calls
go through ``app.meta_client.chat_json_validated`` (structured output,
retried once on invalid JSON). Items already ``verified=False`` are never
sent to the model and stay ``False``; the model can only keep or downgrade,
never upgrade. Inputs are not mutated.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import BaseModel

from app.analyst import format_transcript
from app.fallacy import format_nodes
from app.meta_client import chat_json_validated
from app.schemas import Fallacy, Node, Segment, Speaker

PROMPT_PATH = Path(__file__).resolve().parent / "prompts" / "semantic_verifier.md"
SCHEMA_NAME = "semantic_verdicts"


class SemanticVerdict(BaseModel):
    """One model judgement: whether an item's quote supports its label."""

    id: str
    supported: bool
    reason: str = ""


class SemanticReply(BaseModel):
    """Structured-output shape for the semantic-verifier chat call."""

    verdicts: list[SemanticVerdict]


def load_semantic_prompt() -> str:
    """Read the semantic-verifier system prompt from its prompt file."""
    return PROMPT_PATH.read_text(encoding="utf-8")


def format_node_items(nodes: list[Node]) -> str:
    """Render nodes as ``[node-id] (type=..., speaker=...): text=... | quote=...`` lines."""
    lines = [
        f'[{node.id}] (type={node.type}, speaker={node.speaker}):'
        f' text="{node.text}" | quote="{node.quote}"'
        for node in nodes
    ]
    return "Argument nodes to judge:\n" + "\n".join(lines)


def format_fallacy_items(fallacies: list[Fallacy]) -> str:
    """Render fallacies as ``[fallacy-id] (fallacy=..., node=...): ...`` lines."""
    lines = [
        f"[{fallacy.id}] (fallacy={fallacy.name}, node={fallacy.node_id}):"
        f' explanation="{fallacy.explanation}" | quote="{fallacy.quote}"'
        for fallacy in fallacies
    ]
    return "Fallacies to judge:\n" + "\n".join(lines)


def build_node_messages(
    nodes: list[Node],
    segments: list[Segment],
    speakers: list[Speaker] | None = None,
) -> list[dict[str, Any]]:
    """System prompt + rendered transcript and node items for the chat call."""
    return [
        {"role": "system", "content": load_semantic_prompt()},
        {
            "role": "user",
            "content": format_transcript(speakers or [], segments)
            + "\n"
            + format_node_items(nodes)
            + "\nJudge each item now.",
        },
    ]


def build_fallacy_messages(
    fallacies: list[Fallacy],
    segments: list[Segment],
    nodes: list[Node] | None = None,
    speakers: list[Speaker] | None = None,
) -> list[dict[str, Any]]:
    """System prompt + rendered transcript, node context, and fallacy items."""
    context = format_nodes(nodes) + "\n" if nodes else ""
    return [
        {"role": "system", "content": load_semantic_prompt()},
        {
            "role": "user",
            "content": format_transcript(speakers or [], segments)
            + "\n"
            + context
            + format_fallacy_items(fallacies)
            + "\nJudge each item now.",
        },
    ]


def _verdict_by_id(reply: SemanticReply) -> dict[str, bool]:
    """Map verdicts by item id; later duplicates win, unknown ids pass through."""
    verdicts: dict[str, bool] = {}
    for verdict in reply.verdicts:
        verdicts[verdict.id] = verdict.supported
    return verdicts


def verify_nodes_semantic(
    nodes: list[Node],
    segments: list[Segment],
    speakers: list[Speaker] | None = None,
    *,
    model: str | None = None,
    client: Any | None = None,
) -> list[Node]:
    """Ask the model whether each still-verified node's quote supports its label.

    Nodes already ``verified=False`` are never sent to the model and stay
    ``False``. A ``supported=false`` verdict downgrades its node to
    ``verified=False``; anything else keeps ``verified=True``. Missing or
    unknown verdict ids change nothing. ``model`` defaults to
    ``META_TEXT_MODEL``. Pass ``client`` only in tests. MetaClientError from
    ``meta_client`` propagates unchanged after its retry.
    """
    if not nodes:
        return []
    eligible = [node for node in nodes if node.verified]
    if not eligible:
        return [node.model_copy(update={"verified": False}) for node in nodes]
    messages = build_node_messages(eligible, segments, speakers)
    reply = chat_json_validated(
        messages,
        response_model=SemanticReply,
        schema_name=SCHEMA_NAME,
        model=model,
        client=client,
    )
    by_id = _verdict_by_id(reply)
    checked = []
    for node in nodes:
        if not node.verified or by_id.get(node.id) is False:
            checked.append(node.model_copy(update={"verified": False}))
        else:
            checked.append(node.model_copy(update={"verified": True}))
    return checked


def verify_fallacies_semantic(
    fallacies: list[Fallacy],
    segments: list[Segment],
    nodes: list[Node] | None = None,
    speakers: list[Speaker] | None = None,
    *,
    model: str | None = None,
    client: Any | None = None,
) -> list[Fallacy]:
    """Ask the model whether each still-verified fallacy's quote shows its name.

    Same keep-or-downgrade contract as :func:`verify_nodes_semantic`: items
    already ``verified=False`` skip the model call and stay ``False``; only a
    ``supported=false`` verdict for a listed id downgrades. ``model`` defaults
    to ``META_TEXT_MODEL``. Pass ``client`` only in tests.
    """
    if not fallacies:
        return []
    eligible = [fallacy for fallacy in fallacies if fallacy.verified]
    if not eligible:
        return [fallacy.model_copy(update={"verified": False}) for fallacy in fallacies]
    messages = build_fallacy_messages(eligible, segments, nodes, speakers)
    reply = chat_json_validated(
        messages,
        response_model=SemanticReply,
        schema_name=SCHEMA_NAME,
        model=model,
        client=client,
    )
    by_id = _verdict_by_id(reply)
    checked = []
    for fallacy in fallacies:
        if not fallacy.verified or by_id.get(fallacy.id) is False:
            checked.append(fallacy.model_copy(update={"verified": False}))
        else:
            checked.append(fallacy.model_copy(update={"verified": True}))
    return checked
