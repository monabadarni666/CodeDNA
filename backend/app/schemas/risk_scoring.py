from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.git_impact import GitImpactRequest


class ChangeRiskRequest(GitImpactRequest):
    pass


class SymbolRiskResponse(BaseModel):
    old_path: str | None
    new_path: str | None
    qualified_name: str

    kind: Literal["function", "method"]

    change_type: Literal[
        "added",
        "deleted",
        "modified",
    ]

    graph_matched: bool

    score: int | None = Field(
        ge=0,
        le=100,
    )

    level: Literal[
        "low",
        "medium",
        "high",
        "unknown",
    ]

    direct_count: int
    indirect_count: int
    impacted_file_count: int

    direct_callers: list[str]
    indirect_callers: list[str]
    reasons: list[str]


class ChangeRiskResponse(BaseModel):
    repository: str
    base_commit: str
    target_commit: str

    changed_symbol_count: int
    scored_count: int
    unknown_count: int

    highest_level: Literal[
        "none",
        "low",
        "medium",
        "high",
        "unknown",
    ]

    methodology: str
    items: list[SymbolRiskResponse]
