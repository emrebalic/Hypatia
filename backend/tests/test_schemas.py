"""Schema tests: validate fixtures/sample_debate.json against the SPEC.md contract."""

import copy
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.schemas import DebateResult

FIXTURE = Path(__file__).resolve().parents[2] / "fixtures" / "sample_debate.json"


def load_fixture() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def validate(data: dict) -> DebateResult:
    validate_fn = getattr(DebateResult, "model_validate", None)
    if callable(validate_fn):
        return validate_fn(data)
    return DebateResult.parse_obj(data)  # pydantic v1 fallback


def test_sample_debate_fixture_is_valid():
    result = validate(load_fixture())
    assert len(result.speakers) == 2
    assert len(result.segments) == 11
    assert len(result.nodes) == 9
    assert len(result.edges) == 8
    assert len(result.fallacies) == 3

    by_id = {n.id: n for n in result.nodes}
    assert by_id["n1"].type == "conclusion"
    assert by_id["n2"].type == "premise"
    assert by_id["n4"].type == "rebuttal"
    assert by_id["n9"].segment_ids == ["seg_11"]
    assert by_id["n9"].verified is True

    assert result.edges[0].source == "n2"
    assert result.edges[0].target == "n1"
    assert result.edges[0].relation == "supports"
    assert {e.relation for e in result.edges} <= {"supports", "attacks"}

    fallacy_names = {f.name for f in result.fallacies}
    assert "Straw man" in fallacy_names
    assert result.fallacies[0].node_id == "n5"
    assert result.fallacies[0].verified is True

    assert result.segments[0].start == 0.0
    assert result.segments[0].end == 9.0
    assert isinstance(result.nodes[0].start, float)


def test_rejects_unknown_node_type():
    data = load_fixture()
    data["nodes"][0]["type"] = "opinion"
    with pytest.raises(ValidationError):
        validate(data)


def test_rejects_unknown_edge_relation():
    data = load_fixture()
    data["edges"][0]["relation"] = "refutes"
    with pytest.raises(ValidationError):
        validate(data)


def test_rejects_missing_required_field():
    data = load_fixture()
    del data["nodes"][0]["quote"]
    with pytest.raises(ValidationError):
        validate(data)


def test_round_trip_serialization():
    result = validate(load_fixture())
    dump_fn = getattr(result, "model_dump", None)
    raw = dump_fn() if callable(dump_fn) else result.dict()
    assert validate(copy.deepcopy(raw)) == result
