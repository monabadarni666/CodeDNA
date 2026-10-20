from dataclasses import asdict

from fastapi import APIRouter, HTTPException

from app.analysis.dependency_graph import (
    build_dependency_graph,
    find_impact_candidates,
)
from app.analysis.python_parser import analyze_python_file
from app.analysis.symbol_resolver import resolve_local_calls
from app.api.routes.analysis import get_repository_root
from app.schemas.graph import (
    DependencyGraphRequest,
    DependencyGraphResponse,
    GraphEdge,
    GraphImpact,
    GraphNode,
)

router = APIRouter(
    prefix="/repositories",
    tags=["Dependency Graph"],
)


@router.post(
    "/dependency-graph",
    response_model=DependencyGraphResponse,
)
def dependency_graph_endpoint(
    request: DependencyGraphRequest,
) -> DependencyGraphResponse:
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

        graph = build_dependency_graph(
            analysis=analysis,
            resolutions=resolutions,
            file_id=request.file,
        )

    except ValueError as exc:
        raise HTTPException(
            status_code=422,
            detail=str(exc),
        ) from exc

    except OSError as exc:
        raise HTTPException(
            status_code=500,
            detail="Unable to build dependency graph",
        ) from exc

    impact = None

    if request.changed_symbol is not None:
        changed_id = (
            f"{request.file}::{request.changed_symbol}"
        )

        if changed_id not in graph:
            raise HTTPException(
                status_code=404,
                detail="Changed symbol not found in graph",
            )

        impact_result = find_impact_candidates(
            graph,
            changed_id,
        )

        impact = GraphImpact(**asdict(impact_result))

    nodes = [
        GraphNode(id=node_id, **attributes)
        for node_id, attributes in graph.nodes(data=True)
    ]

    edges = [
        GraphEdge(
            source=source,
            target=target,
            **attributes,
        )
        for source, target, attributes in graph.edges(
            data=True
        )
    ]

    return DependencyGraphResponse(
        repository=request.repository,
        file=request.file,
        node_count=graph.number_of_nodes(),
        edge_count=graph.number_of_edges(),
        nodes=nodes,
        edges=edges,
        impact=impact,
    )
