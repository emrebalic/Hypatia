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

import re
from difflib import SequenceMatcher

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


def quote_in_scope(quote: str, scope: list[Segment], segments: list[Segment]) -> bool:
    """True when ``quote`` is grounded in the given segment scope.

    The quote must appear inside one scoped segment, or across a run of
    scoped segments that are consecutive in the transcript (a sentence
    split by a speaker-turn boundary). Joining non-consecutive segments
    never creates a match, so a quote borrowed from an unlisted part of
    the transcript fails even when its timestamp was moved into scope.
    """
    if not scope:
        return False
    order = {segment.id: index for index, segment in enumerate(segments)}
    ordered = sorted(scope, key=lambda segment: order.get(segment.id, len(order)))
    groups: list[list[Segment]] = [[ordered[0]]]
    for segment in ordered[1:]:
        previous = groups[-1][-1]
        if order.get(segment.id, -2) == order.get(previous.id, -1) + 1:
            groups[-1].append(segment)
        else:
            groups.append([segment])
    return any(
        quote_in_text(quote, " ".join(item.text for item in group)) for group in groups
    )


_TOKEN_RE = re.compile(r"\S+")
_TOKEN_STRIP = ".,!?;:\"'()[]{}<>*"


def _token_spans(text: str) -> list[tuple[str, int, int]]:
    """(normalized token, start, end) for every whitespace token in ``text``."""
    return [
        (match.group(0).strip(_TOKEN_STRIP).lower(), match.start(), match.end())
        for match in _TOKEN_RE.finditer(text)
    ]


def ground_quote(
    quote: str,
    segments: list[Segment],
    preferred_ids: list[str] | None = None,
) -> tuple[str, Segment] | None:
    """Snap a model quote to the exact words in one transcript segment.

    Models tend to "clean up" speech (dropping stutters and fillers), which
    then fails verbatim verification even though the words are there. This
    returns ``(exact_quote, segment)`` where ``exact_quote`` is a contiguous
    span of the segment's own text: first an exact token-sequence match,
    otherwise the best token alignment covering at least 70% of the quote.
    Preferred segments are searched first, then the whole transcript, so a
    wrong ``segment_ids`` guess by the model is corrected too. Returns None
    when nothing in the transcript resembles the quote.
    """
    quote_tokens = [token for token, _, _ in _token_spans(quote)]
    if not quote_tokens:
        return None
    by_id = {segment.id: segment for segment in segments}
    ordered: list[Segment] = []
    for segment_id in preferred_ids or []:
        segment = by_id.get(segment_id)
        if segment is not None and segment not in ordered:
            ordered.append(segment)
    ordered.extend(segment for segment in segments if segment not in ordered)
    # Exact token-sequence match anywhere in the search order.
    for segment in ordered:
        spans = _token_spans(segment.text)
        tokens = [token for token, _, _ in spans]
        for offset in range(len(tokens) - len(quote_tokens) + 1):
            if tokens[offset : offset + len(quote_tokens)] == quote_tokens:
                start = spans[offset][1]
                end = spans[offset + len(quote_tokens) - 1][2]
                return segment.text[start:end], segment
    # Fuzzy match: align the quote tokens against each segment and take the
    # segment span from the first to the last matched token.
    best: tuple[float, str, Segment] | None = None
    for segment in ordered:
        spans = _token_spans(segment.text)
        tokens = [token for token, _, _ in spans]
        if not tokens:
            continue
        matcher = SequenceMatcher(a=quote_tokens, b=tokens, autojunk=False)
        blocks = [block for block in matcher.get_matching_blocks() if block.size]
        if not blocks:
            continue
        coverage = sum(block.size for block in blocks) / len(quote_tokens)
        if coverage < 0.7:
            continue
        first = blocks[0].b
        last_block = blocks[-1]
        last = last_block.b + last_block.size - 1
        if last - first + 1 > max(len(quote_tokens) * 2, len(quote_tokens) + 6):
            continue
        exact = segment.text[spans[first][1] : spans[last][2]]
        if best is None or coverage > best[0]:
            best = (coverage, exact, segment)
    if best is None:
        return None
    return best[1], best[2]


def ground_nodes(nodes: list[Node], segments: list[Segment]) -> list[Node]:
    """Return node copies whose quotes are exact transcript spans.

    Grounding also corrects ``segment_ids``, ``speaker`` and (when it falls
    outside the grounded segment) ``start`` from the segment the quote was
    actually found in. Nodes whose quote resembles nothing in the
    transcript are returned unchanged and will fail verification.
    """
    grounded = []
    for node in nodes:
        found = ground_quote(node.quote, segments, node.segment_ids)
        if found is None:
            grounded.append(node)
            continue
        exact, segment = found
        grounded.append(
            node.model_copy(
                update={
                    "quote": exact,
                    "segment_ids": [segment.id],
                    "speaker": segment.speaker,
                    "start": node.start if segment.start <= node.start <= segment.end else segment.start,
                }
            )
        )
    return grounded


def ground_fallacies(
    fallacies: list[Fallacy],
    segments: list[Segment],
    nodes: list[Node] | None = None,
) -> list[Fallacy]:
    """Return fallacy copies whose quotes are exact transcript spans."""
    by_node = {node.id: node for node in nodes or []}
    grounded = []
    for fallacy in fallacies:
        linked = by_node.get(fallacy.node_id)
        found = ground_quote(
            fallacy.quote, segments, linked.segment_ids if linked else None
        )
        if found is None:
            grounded.append(fallacy)
            continue
        exact, _segment = found
        # Only the quote is snapped: a fallacy's start stays as the model
        # gave it, so an out-of-range timestamp still fails verification.
        grounded.append(fallacy.model_copy(update={"quote": exact}))
    return grounded


def start_in_segments(start: float, segments: list[Segment]) -> bool:
    """True when ``start`` falls inside any of the given segments (inclusive)."""
    return any(segment.start <= start <= segment.end for segment in segments)


def verify_nodes(nodes: list[Node], segments: list[Segment]) -> list[Node]:
    """Return node copies with ``verified`` set by the deterministic checks.

    A node passes when its ``quote`` is grounded in its listed
    ``segment_ids`` (see ``quote_in_scope``) and its ``start`` falls inside
    one of them. Unknown or missing segment ids fail both checks, so the
    node is unverified.
    """
    by_id = {segment.id: segment for segment in segments}
    verified_nodes = []
    for node in nodes:
        scope = [by_id[sid] for sid in node.segment_ids if sid in by_id]
        ok = quote_in_scope(node.quote, scope, segments) and start_in_segments(
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

    A fallacy passes when its ``quote`` is grounded in its linked node's
    segments (see ``quote_in_scope``) and its ``start`` falls inside them.
    When no ``nodes`` are given or the link does not resolve, the scope is
    the whole transcript.
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
        ok = quote_in_scope(fallacy.quote, scope, segments) and start_in_segments(
            fallacy.start, scope
        )
        verified_fallacies.append(fallacy.model_copy(update={"verified": ok}))
    return verified_fallacies
