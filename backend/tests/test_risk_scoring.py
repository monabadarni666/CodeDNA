from app.analysis.git_change_impact import (
    GitImpactReport,
    SymbolImpact,
)
from app.analysis.risk_scoring import (
    assess_symbol_risk,
    rank_change_risks,
)


def make_change(
    *,
    name: str = "get_user",
    change_type: str = "modified",
    matched: bool = True,
    direct: tuple[str, ...] = (),
    indirect: tuple[str, ...] = (),
) -> SymbolImpact:
    return SymbolImpact(
        old_path="app/services/users.py",
        new_path="app/services/users.py",
        qualified_name=name,
        kind="function",
        change_type=change_type,
        graph_matched=matched,
        direct_callers=list(direct),
        indirect_callers=list(indirect),
    )


def test_modified_cross_package_risk() -> None:
    change = make_change(
        direct=("app/auth.py::login",),
        indirect=("main.py::start",),
    )

    risk = assess_symbol_risk(change)

    assert risk.score == 43
    assert risk.level == "medium"
    assert risk.direct_count == 1
    assert risk.indirect_count == 1
    assert risk.impacted_file_count == 2
    assert len(risk.reasons) == 4


def test_added_has_lower_baseline_than_deleted() -> None:
    added = assess_symbol_risk(
        make_change(change_type="added")
    )

    deleted = assess_symbol_risk(
        make_change(change_type="deleted")
    )

    assert added.score == 8
    assert added.level == "low"

    assert deleted.score == 25
    assert deleted.level == "medium"


def test_unknown_graph_does_not_get_low_risk() -> None:
    risk = assess_symbol_risk(
        make_change(matched=False)
    )

    assert risk.score is None
    assert risk.level == "unknown"
    assert risk.reasons


def test_score_is_capped_at_100() -> None:
    direct = tuple(
        f"direct_{index}/api.py::handler"
        for index in range(10)
    )

    indirect = tuple(
        f"indirect_{index}/service.py::caller"
        for index in range(10)
    )

    risk = assess_symbol_risk(
        make_change(
            change_type="deleted",
            direct=direct,
            indirect=indirect,
        )
    )

    assert risk.score == 100
    assert risk.level == "high"


def test_same_file_is_not_cross_file_impact() -> None:
    risk = assess_symbol_risk(
        make_change(
            direct=(
                "app/services/users.py::lookup",
            )
        )
    )

    assert risk.direct_count == 1
    assert risk.impacted_file_count == 0
    assert risk.score == 27


def test_duplicate_callers_are_not_double_counted() -> None:
    risk = assess_symbol_risk(
        make_change(
            direct=(
                "app/auth.py::login",
                "app/auth.py::login",
            ),
            indirect=(
                "app/auth.py::login",
            ),
        )
    )

    assert risk.direct_count == 1
    assert risk.indirect_count == 0
    assert risk.impacted_file_count == 1
    assert risk.score == 32


def test_report_orders_high_risk_before_unknown() -> None:
    high = make_change(
        name="critical",
        change_type="deleted",
        direct=tuple(
            f"api_{index}.py::handler"
            for index in range(6)
        ),
    )

    low = make_change(
        name="small",
        change_type="added",
    )

    unknown = make_change(
        name="unresolved",
        matched=False,
    )

    source = GitImpactReport(
        base_commit="a" * 40,
        target_commit="b" * 40,
        changed_symbol_count=3,
        changes=[unknown, low, high],
    )

    report = rank_change_risks(source)

    assert report.items[0].qualified_name == "critical"
    assert report.items[1].qualified_name == "small"
    assert report.items[2].qualified_name == "unresolved"

    assert report.highest_level == "high"
    assert report.scored_count == 2
    assert report.unknown_count == 1


def test_empty_report_has_no_risk() -> None:
    source = GitImpactReport(
        base_commit="a" * 40,
        target_commit="b" * 40,
        changed_symbol_count=0,
        changes=[],
    )

    report = rank_change_risks(source)

    assert report.items == []
    assert report.scored_count == 0
    assert report.unknown_count == 0
    assert report.highest_level == "none"
