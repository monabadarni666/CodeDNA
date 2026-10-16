from dataclasses import asdict

from fastapi import APIRouter, HTTPException

from app.analysis.scanner import scan_repository
from app.core.config import WORKSPACES_DIR
from app.schemas.repository import (
    RepositoryScanRequest,
    RepositoryScanResponse,
)

router = APIRouter(
    prefix="/repositories",
    tags=["Repositories"],
)


@router.post(
    "/scan",
    response_model=RepositoryScanResponse,
)
def scan_repository_endpoint(
    request: RepositoryScanRequest,
) -> RepositoryScanResponse:
    workspace_root = WORKSPACES_DIR.resolve()

    if not workspace_root.is_dir():
        raise HTTPException(
            status_code=503,
            detail="Workspace directory is unavailable",
        )

    repository_path = workspace_root / request.repository

    if repository_path.is_symlink():
        raise HTTPException(
            status_code=400,
            detail="Repository symlinks are not allowed",
        )

    resolved_path = repository_path.resolve()

    if resolved_path.parent != workspace_root:
        raise HTTPException(
            status_code=403,
            detail="Repository is outside the allowed workspace",
        )

    if not resolved_path.is_dir():
        raise HTTPException(
            status_code=404,
            detail="Repository not found",
        )

    try:
        result = scan_repository(resolved_path)
    except OSError as exc:
        raise HTTPException(
            status_code=500,
            detail="Repository scan failed",
        ) from exc

    return RepositoryScanResponse(**asdict(result))
