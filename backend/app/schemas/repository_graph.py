from pydantic import BaseModel, Field

from app.schemas.graph import GraphEdge, GraphImpact, GraphNode


class RepositoryGraphRequest(BaseModel):
    repository: str = Field(
        min_length=1,
        max_length=128,
    )
    changed_symbol: str | None = Field(
        default=None,
        min_length=1,
        max_length=512,
        description=(
            "Optional full graph node ID, "
            "for example database.py::get_user"
        ),
    )


class RepositoryGraphResponse(BaseModel):
    repository: str
    file_count: int
    node_count: int
    edge_count: int
    nodes: list[GraphNode]
    edges: list[GraphEdge]
    impact: GraphImpact | None
