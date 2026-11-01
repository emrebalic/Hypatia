"""Pydantic models for the Hypatia data contract.

Single source of truth per SPEC.md ("Data contract"). Field names and shapes
match SPEC.md exactly; cross-item rules (quotes verbatim in transcript,
timestamps inside segments) are enforced by the verifier (TASKS.md task 8),
not here.
"""

from typing import Literal

from pydantic import BaseModel

NodeType = Literal["claim", "premise", "conclusion", "rebuttal"]
Relation = Literal["supports", "attacks"]


class Speaker(BaseModel):
    id: str
    label: str


class Segment(BaseModel):
    id: str
    speaker: str
    start: float
    end: float
    text: str


class Node(BaseModel):
    id: str
    type: NodeType
    speaker: str
    text: str
    quote: str
    start: float
    segment_ids: list[str]
    verified: bool


class Edge(BaseModel):
    source: str
    target: str
    relation: Relation


class Fallacy(BaseModel):
    id: str
    node_id: str
    name: str
    explanation: str
    quote: str
    start: float
    verified: bool


class DebateResult(BaseModel):
    speakers: list[Speaker]
    segments: list[Segment]
    nodes: list[Node]
    edges: list[Edge]
    fallacies: list[Fallacy]


# Aliases for future pipeline/UI code; all refer to the same contract models.
ArgumentNode = Node
Debate = DebateResult
AnalysisResult = DebateResult
