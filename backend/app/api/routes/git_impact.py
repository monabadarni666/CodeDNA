from dataclasses import asdict

from fastapi import APIRouter, HTTPException

from app.analysis.git_change_impact import (
    analyze_git_change_impact,
)
from app.analysis.git_diff_analyzer import GitDiffError
from app.api.routes.analysis import get_repository_root
from app.schemas.git_impact import (
    GitImpactRequest,
    GitImpactResponse,
    SymbolImpactResponse,
)

router = APIRouter(
    prefix="/repositories",
    tags=["Git Change Impact"],
)


@router.post(
    "/change-impact",
    response_model=GitImpactResponse,
)
def git_change_impact_endpoint(
    request: GitImpactRequest,
) -> GitImpactResponse:
    repository_root = get_repository_root(
        request.repository
    )

    try:
        report = analyze_git_change_impact(
            repository_root,
            request.base_revision,
            request.target_revision,
        )

    except (GitDiffError, ValueError) as exc:
        raise HTTPException(
            status_code=422,
            detail=str(exc),
        ) from exc

    except OSError as exc:
        raise HTTPException(
            status_code=500,
            detail="Unable to analyze Git change impact",
        ) from exc

    return GitImpactResponse(
        repository=request.repository,
        base_commit=report.base_commit,
        target_commit=report.target_commit,
        changed_symbol_count=(
            report.changed_symbol_count
        ),
        changes=[
            SymbolImpactResponse(
                **asdict(change)
            )
            for change in report.changes
        ],
    )
