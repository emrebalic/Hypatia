"""Offline tests for the deterministic verifier (app.verifier).

No model calls are involved. Good inputs come from fixtures/sample_debate.json
and fixtures/analyst_reply.json; broken cases are deliberately corrupted copies
(invented quotes, out-of-range timestamps, unknown segment ids).
"""

import copy
import json
from pathlib import Path

from app.schemas import Fallacy, Node, Segment
from app.verifier import (
    normalize,
    quote_in_text,
    verify_fallacies,
    verify_nodes,
)

FIXTURES = Path(__file__).resolve().parents[2] / "fixtures"


def _load() -> tuple[list[Segment], list[Node], list[Fallacy]]:
    debate = json.loads((FIXTURES / "sample_debate.json").read_text(encoding="utf-8"))
    segments = [Segment.model_validate(item) for item in debate["segments"]]
    nodes = [Node.model_validate(item) for item in debate["nodes"]]
    fallacies = [Fallacy.model_validate(item) for item in debate["fallacies"]]
    return segments, nodes, fallacies


def test_matching_is_case_and_whitespace_insensitive():
    assert normalize("  Hello   WORLD\n") == "hello world"
    assert quote_in_text("  REMOTE   work SHOULD be", "remote work should be here")
    assert not quote_in_text("   ", "remote work should be here")
    assert not quote_in_text("", "remote work should be here")


def test_good_nodes_all_verify():
    segments, nodes, _ = _load()
    checked = verify_nodes(nodes, segments)
    assert [node.id for node in checked] == [node.id for node in nodes]
    assert all(node.verified is True for node in checked)
    # Inputs are not mutated.
    assert all(node.verified is True for node in nodes)


def test_invented_quote_fails_while_rest_pass():
    segments, nodes, _ = _load()
    broken = copy.deepcopy(nodes)
    broken[0] = broken[0].model_copy(
        update={"quote": "Remote work cures every disease known to science."}
    )
    checked = verify_nodes(broken, segments)
    by_id = {node.id: node for node in checked}
    assert by_id["n1"].verified is False
    assert all(node.verified is True for node in checked if node.id != "n1")
    # The caller's objects keep their own flags.
    assert broken[0].verified is True


def test_timestamp_outside_segment_fails():
    segments, nodes, _ = _load()
    broken = copy.deepcopy(nodes)
    broken[1] = broken[1].model_copy(update={"start": 999.0})
    checked = verify_nodes(broken, segments)
    by_id = {node.id: node for node in checked}
    assert by_id["n2"].verified is False
    assert by_id["n1"].verified is True


def test_case_and_whitespace_variant_quote_still_verifies():
    segments, nodes, _ = _load()
    variant = copy.deepcopy(nodes[0])
    variant = variant.model_copy(
        update={"quote": "  REMOTE   work should BE\nthe default for SOFTWARE teams. "}
    )
    assert verify_nodes([variant], segments)[0].verified is True


def test_unknown_segment_id_fails():
    segments, nodes, _ = _load()
    broken = copy.deepcopy(nodes[0]).model_copy(update={"segment_ids": ["nope"]})
    assert verify_nodes([broken], segments)[0].verified is False
    broken = copy.deepcopy(nodes[0]).model_copy(update={"segment_ids": []})
    assert verify_nodes([broken], segments)[0].verified is False


def test_good_fallacies_all_verify():
    segments, nodes, fallacies = _load()
    checked = verify_fallacies(fallacies, segments, nodes)
    assert all(fallacy.verified is True for fallacy in checked)


def test_broken_fallacy_quote_and_start_fail():
    segments, nodes, fallacies = _load()
    broken = copy.deepcopy(fallacies)
    broken[0] = broken[0].model_copy(
        update={"quote": "Nobody ever said anything about meeting anyone."}
    )
    broken[1] = broken[1].model_copy(update={"start": 999.0})
    checked = verify_fallacies(broken, segments, nodes)
    by_id = {fallacy.id: fallacy for fallacy in checked}
    assert by_id["f1"].verified is False
    assert by_id["f2"].verified is False
    assert by_id["f3"].verified is True
