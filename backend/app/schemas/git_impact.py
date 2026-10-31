from typing import Literal

from pydantic import BaseModel, Field


class GitImpactRequest(BaseModel):
    repository: str = Field(
        min_length=1,
        max_length=128,
    )

    base_revision: str = Field(
        min_length=1,
        max_length=128,
    )

    target_revision: str = Field(
        min_length=1,
        max_length=128,
    )


class SymbolImpactResponse(BaseModel):
    old_path: str | None
    new_path: str | None
    qualified_name: str

    kind: Literal[
        "function",
        "method",
    ]

    change_type: Literal[
        "added",
        "deleted",
        "modified",
    ]

    graph_matched: bool
    direct_callers: list[str]
    indirect_callers: list[str]


class GitImpactResponse(BaseModel):
    repository: str
    base_commit: str
    target_commit: str
    changed_symbol_count: int
    changes: list[SymbolImpactResponse]
