"""Deterministic verifier (task 8): quote + timestamp checks, no model calls.

SPEC.md rules enforced here (``quote`` matched case/whitespace-insensitively):
- every ``quote`` must appear verbatim in the transcript;
- every ``start`` must fall inside its segment.

Failing nodes/fallacies get ``verified=False``; passing ones get
``verified=True``. Inputs are not mutated; verified copies are returned.
The semantic check ("does this quote support this label?") is task 10 and
lives elsewhere; this module is purely textual/temporal.

Fallacies carry no ``segment_ids`` in the contract, so a fallacy's ``start``
is checked against its linked node's segments when ``nodes`` are given and
the link resolves, and against the whole transcript otherwise.
"""

from __future__ import annotations

from app.schemas import Fallacy, Node, Segment


def normalize(text: str) -> str:
    """Lowercase and collapse all whitespace so matching is insensitive to both."""
    return " ".join(text.lower().split())


def quote_in_text(quote: str, text: str) -> bool:
    """True when ``quote`` appears verbatim in ``text`` (case/whitespace-insensitive)."""
    normalized = normalize(quote)
    return bool(normalized) and normalized in normalize(text)


def quote_in_transcript(quote: str, segments: list[Segment]) -> bool:
    """True when ``quote`` appears in any transcript segment."""
    return any(quote_in_text(quote, segment.text) for segment in segments)


def start_in_segments(start: float, segments: list[Segment]) -> bool:
    """True when ``start`` falls inside any of the given segments (inclusive)."""
    return any(segment.start <= start <= segment.end for segment in segments)


def verify_nodes(nodes: list[Node], segments: list[Segment]) -> list[Node]:
    """Return node copies with ``verified`` set by the deterministic checks.

    A node passes when its ``quote`` appears anywhere in the transcript and
    its ``start`` falls inside one of its listed ``segment_ids``. Unknown or
    missing segment ids fail the timestamp check, so the node is unverified.
    """
    by_id = {segment.id: segment for segment in segments}
    verified_nodes = []
    for node in nodes:
        scope = [by_id[sid] for sid in node.segment_ids if sid in by_id]
        ok = quote_in_transcript(node.quote, segments) and start_in_segments(
            node.start, scope
        )
        verified_nodes.append(node.model_copy(update={"verified": ok}))
    return verified_nodes


def verify_fallacies(
    fallacies: list[Fallacy],
    segments: list[Segment],
    nodes: list[Node] | None = None,
) -> list[Fallacy]:
    """Return fallacy copies with ``verified`` set by the deterministic checks.

    A fallacy passes when its ``quote`` appears anywhere in the transcript
    and its ``start`` falls inside its linked node's segments (or inside any
    segment when no ``nodes`` are given or the link does not resolve).
    """
    by_id = {segment.id: segment for segment in segments}
    scope_by_node = {
        node.id: [by_id[sid] for sid in node.segment_ids if sid in by_id]
        for node in nodes or []
    }
    verified_fallacies = []
    for fallacy in fallacies:
        if nodes is None or fallacy.node_id not in scope_by_node:
            scope = list(segments)
        else:
            scope = scope_by_node[fallacy.node_id]
        ok = quote_in_transcript(fallacy.quote, segments) and start_in_segments(
            fallacy.start, scope
        )
        verified_fallacies.append(fallacy.model_copy(update={"verified": ok}))
    return verified_fallacies
