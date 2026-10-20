from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.analysis import PythonAnalysisRequest


class DependencyGraphRequest(PythonAnalysisRequest):
    changed_symbol: str | None = Field(
        default=None,
        min_length=1,
        max_length=256,
        description=(
            "Optional qualified symbol name "
            "for impact analysis"
        ),
    )


class GraphNode(BaseModel):
    id: str
    name: str
    qualified_name: str
    kind: Literal["class", "function", "method"]
    file: str
    line: int
    end_line: int | None


class GraphEdge(BaseModel):
    source: str
    target: str
    relationship: Literal["calls"]
    confidence: Literal["candidate"]
    call_lines: list[int]


class GraphImpact(BaseModel):
    changed_symbol: str
    direct_callers: list[str]
    indirect_callers: list[str]


class DependencyGraphResponse(BaseModel):
    repository: str
    file: str
    node_count: int
    edge_count: int
    nodes: list[GraphNode]
    edges: list[GraphEdge]
    impact: GraphImpact | None
