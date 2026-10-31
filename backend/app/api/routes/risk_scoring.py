from dataclasses import asdict

from fastapi import APIRouter, HTTPException

from app.analysis.git_change_impact import (
    analyze_git_change_impact,
)
from app.analysis.git_diff_analyzer import GitDiffError
from app.analysis.risk_scoring import (
    METHODOLOGY_NOTE,
    rank_change_risks,
)
from app.api.routes.analysis import get_repository_root
from app.schemas.risk_scoring import (
    ChangeRiskRequest,
    ChangeRiskResponse,
    SymbolRiskResponse,
)

router = APIRouter(
    prefix="/repositories",
    tags=["Change Risk Analysis"],
)


@router.post(
    "/change-risk",
    response_model=ChangeRiskResponse,
)
def change_risk_endpoint(
    request: ChangeRiskRequest,
) -> ChangeRiskResponse:
    repository_root = get_repository_root(
        request.repository
    )

    try:
        impact_report = analyze_git_change_impact(
            repository_root,
            request.base_revision,
            request.target_revision,
        )

        risk_report = rank_change_risks(
            impact_report
        )

    except (GitDiffError, ValueError) as exc:
        raise HTTPException(
            status_code=422,
            detail=str(exc),
        ) from exc

    except OSError as exc:
        raise HTTPException(
            status_code=500,
            detail="Unable to calculate change risk",
        ) from exc

    return ChangeRiskResponse(
        repository=request.repository,
        base_commit=risk_report.base_commit,
        target_commit=risk_report.target_commit,
        changed_symbol_count=(
            risk_report.changed_symbol_count
        ),
        scored_count=risk_report.scored_count,
        unknown_count=risk_report.unknown_count,
        highest_level=risk_report.highest_level,
        methodology=METHODOLOGY_NOTE,
        items=[
            SymbolRiskResponse(**asdict(item))
            for item in risk_report.items
        ],
    )
