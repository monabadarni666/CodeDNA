from dataclasses import asdict
from pathlib import Path

from fastapi import APIRouter, HTTPException

from app.analysis.python_parser import analyze_python_file
from app.analysis.symbol_resolver import resolve_local_calls
from app.core.config import WORKSPACES_DIR
from app.schemas.analysis import (
    PythonAnalysisRequest,
    PythonAnalysisResponse,
)

router = APIRouter(
    prefix="/repositories",
    tags=["Code Analysis"],
)


def get_repository_root(repository: str) -> Path:
    workspace_root = WORKSPACES_DIR.resolve()

    if not workspace_root.is_dir():
        raise HTTPException(
            status_code=503,
            detail="Workspace directory is unavailable",
        )

    repository_path = workspace_root / repository

    if repository_path.is_symlink():
        raise HTTPException(
            status_code=400,
            detail="Repository symlinks are not allowed",
        )

    repository_root = repository_path.resolve()

    if repository_root.parent != workspace_root:
        raise HTTPException(
            status_code=403,
            detail="Repository is outside the workspace",
        )

    if not repository_root.is_dir():
        raise HTTPException(
            status_code=404,
            detail="Repository not found",
        )

    return repository_root


@router.post(
    "/analyze-python",
    response_model=PythonAnalysisResponse,
)
def analyze_python_endpoint(
    request: PythonAnalysisRequest,
) -> PythonAnalysisResponse:
    repository_root = get_repository_root(
        request.repository
    )

    file_path = repository_root

    for part in request.file.split("/"):
        file_path = file_path / part

        if file_path.is_symlink():
            raise HTTPException(
                status_code=400,
                detail="File symlinks are not allowed",
            )

    resolved_file = file_path.resolve()

    if not resolved_file.is_relative_to(repository_root):
        raise HTTPException(
            status_code=403,
            detail="File is outside the repository",
        )

    if not resolved_file.is_file():
        raise HTTPException(
            status_code=404,
            detail="Python file not found",
        )

    try:
        analysis = analyze_python_file(resolved_file)
        resolutions = resolve_local_calls(analysis)

    except ValueError as exc:
        raise HTTPException(
            status_code=422,
            detail=str(exc),
        ) from exc

    except OSError as exc:
        raise HTTPException(
            status_code=500,
            detail="Unable to analyze Python file",
        ) from exc

    return PythonAnalysisResponse(
        repository=request.repository,
        file=request.file,
        symbols=[
            asdict(item) for item in analysis.symbols
        ],
        imports=[
            asdict(item) for item in analysis.imports
        ],
        calls=[
            asdict(item) for item in analysis.calls
        ],
        resolutions=[
            asdict(item) for item in resolutions
        ],
        other_bindings=analysis.other_bindings,
    )
