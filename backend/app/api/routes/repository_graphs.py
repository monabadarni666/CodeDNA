from dataclasses import asdict

from fastapi import APIRouter, HTTPException

from app.analysis.dependency_graph import find_impact_candidates
from app.analysis.repository_graph import (
    build_repository_dependency_graph,
)
from app.api.routes.analysis import get_repository_root
from app.schemas.graph import GraphEdge, GraphImpact, GraphNode
from app.schemas.repository_graph import (
    RepositoryGraphRequest,
    RepositoryGraphResponse,
)

router = APIRouter(
    prefix="/repositories",
    tags=["Repository Dependency Graph"],
)


@router.post(
    "/graph",
    response_model=RepositoryGraphResponse,
)
def repository_graph_endpoint(
    request: RepositoryGraphRequest,
) -> RepositoryGraphResponse:
    repository_root = get_repository_root(
        request.repository
    )

    try:
        graph = build_repository_dependency_graph(
            repository_root
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=422,
            detail=str(exc),
        ) from exc
    except OSError as exc:
        raise HTTPException(
            status_code=500,
            detail="Unable to build repository graph",
        ) from exc

    impact = None

    if request.changed_symbol is not None:
        if request.changed_symbol not in graph:
            raise HTTPException(
                status_code=404,
                detail="Changed symbol not found in graph",
            )

        impact_result = find_impact_candidates(
            graph,
            request.changed_symbol,
        )

        impact = GraphImpact(
            **asdict(impact_result)
        )

    nodes = [
        GraphNode(
            id=node_id,
            **attributes,
        )
        for node_id, attributes in graph.nodes(
            data=True
        )
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

    return RepositoryGraphResponse(
        repository=request.repository,
        file_count=graph.graph["file_count"],
        node_count=graph.number_of_nodes(),
        edge_count=graph.number_of_edges(),
        nodes=nodes,
        edges=edges,
        impact=impact,
    )
