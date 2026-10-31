from dataclasses import dataclass
from typing import Literal

from app.analysis.git_change_impact import (
    GitImpactReport,
    SymbolImpact,
)

RiskLevel = Literal["low", "medium", "high", "unknown"]
HighestRisk = Literal[
    "none", "low", "medium", "high", "unknown"
]

METHODOLOGY_NOTE = (
    "Deterministic impact heuristic, not a probability "
    "of a bug. Scores use change type, candidate direct "
    "and indirect callers, and distinct caller files. "
    "Only detected Python functions and methods are scored. "
    "Dynamic dependencies, module-level changes, and "
    "unsupported relationships may be missed."
)

BASE_POINTS = {
    "added": 8,
    "modified": 15,
    "deleted": 25,
}


@dataclass(frozen=True)
class SymbolRisk:
    old_path: str | None
    new_path: str | None
    qualified_name: str
    kind: str
    change_type: str
    graph_matched: bool
    score: int | None
    level: RiskLevel
    direct_count: int
    indirect_count: int
    impacted_file_count: int
    direct_callers: list[str]
    indirect_callers: list[str]
    reasons: list[str]


@dataclass(frozen=True)
class ChangeRiskReport:
    base_commit: str
    target_commit: str
    changed_symbol_count: int
    scored_count: int
    unknown_count: int
    highest_level: HighestRisk
    items: list[SymbolRisk]


def assess_symbol_risk(
    change: SymbolImpact,
) -> SymbolRisk:
    direct = sorted(set(change.direct_callers))
    indirect = sorted(
        set(change.indirect_callers) - set(direct)
    )

    changed_paths = {
        path
        for path in (
            change.old_path,
            change.new_path,
        )
        if path is not None
    }

    caller_paths = {
        caller.split("::", 1)[0]
        for caller in (*direct, *indirect)
        if "::" in caller
    }

    caller_paths.difference_update(changed_paths)

    direct_count = len(direct)
    indirect_count = len(indirect)
    impacted_file_count = len(caller_paths)

    common = {
        "old_path": change.old_path,
        "new_path": change.new_path,
        "qualified_name": change.qualified_name,
        "kind": change.kind,
        "change_type": change.change_type,
        "graph_matched": change.graph_matched,
        "direct_count": direct_count,
        "indirect_count": indirect_count,
        "impacted_file_count": impacted_file_count,
        "direct_callers": direct,
        "indirect_callers": indirect,
    }

    if not change.graph_matched:
        return SymbolRisk(
            **common,
            score=None,
            level="unknown",
            reasons=[
                ("Symbol could not be matched to a "
                "supported dependency graph node. "
                "Risk cannot be scored reliably.")
            ],
        )

    if change.change_type not in BASE_POINTS:
        raise ValueError(
            f"Unsupported change type: {change.change_type}"
        )

    base_points = BASE_POINTS[change.change_type]
    direct_points = min(36, direct_count * 12)
    indirect_points = min(24, indirect_count * 6)
    file_points = min(15, impacted_file_count * 5)

    score = min(
        100,
        base_points
        + direct_points
        + indirect_points
        + file_points,
    )

    if score >= 55:
        level: RiskLevel = "high"
    elif score >= 25:
        level = "medium"
    else:
        level = "low"

    reasons = [
        (
            f"{change.change_type.capitalize()} symbol: "
            f"+{base_points} baseline points."
        ),
        (
            f"{direct_count} direct caller candidates: "
            f"+{direct_points} points."
        ),
        (
            f"{indirect_count} indirect caller candidates: "
            f"+{indirect_points} points."
        ),
        (
            f"{impacted_file_count} distinct other caller "
            f"files: +{file_points} points."
        ),
    ]

    return SymbolRisk(
        **common,
        score=score,
        level=level,
        reasons=reasons,
    )


def rank_change_risks(
    report: GitImpactReport,
) -> ChangeRiskReport:
    items = [
        assess_symbol_risk(change)
        for change in report.changes
    ]

    # Higher scores first; unknown scores last.
    items.sort(
        key=lambda item: (
            item.score is None,
            -(item.score or 0),
            item.new_path or item.old_path or "",
            item.qualified_name,
        )
    )

    scored_count = sum(
        item.score is not None
        for item in items
    )

    unknown_count = len(items) - scored_count

    severity_order = {
        "low": 1,
        "medium": 2,
        "high": 3,
    }

    scored_levels = [
        item.level
        for item in items
        if item.score is not None
    ]

    if scored_levels:
        highest_level: HighestRisk = max(
            scored_levels,
            key=lambda level: severity_order[level],
        )
    elif unknown_count:
        highest_level = "unknown"
    else:
        highest_level = "none"

    return ChangeRiskReport(
        base_commit=report.base_commit,
        target_commit=report.target_commit,
        changed_symbol_count=report.changed_symbol_count,
        scored_count=scored_count,
        unknown_count=unknown_count,
        highest_level=highest_level,
        items=items,
    )
