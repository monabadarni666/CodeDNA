from pathlib import Path

import networkx as nx

from app.analysis.cross_file import find_cross_file_calls
from app.analysis.dependency_graph import build_dependency_graph
from app.analysis.module_discovery import discover_python_modules
from app.analysis.python_parser import analyze_python_file
from app.analysis.symbol_resolver import resolve_local_calls


def build_repository_dependency_graph(
    repository_root: str | Path,
) -> nx.DiGraph:
    """
    Build a dependency graph across discovered Python modules.

    Supports:
    - Root-level Python modules
    - Regular Python packages
    - Local candidate call relationships
    - Supported cross-file and cross-package imports

    Edges are static candidates, not guaranteed
    runtime dependencies.
    """
    root = Path(repository_root).expanduser()

    modules = discover_python_modules(root)

    graph = nx.DiGraph(
        repository=str(root),
        file_count=len(modules),
    )

    # Build the local graph of every discovered module.
    for module in modules:
        analysis = analyze_python_file(module.path)

        resolutions = resolve_local_calls(analysis)

        file_graph = build_dependency_graph(
            analysis=analysis,
            resolutions=resolutions,
            file_id=module.relative_path,
        )

        graph.add_nodes_from(
            file_graph.nodes(data=True)
        )

        graph.add_edges_from(
            file_graph.edges(data=True)
        )

    # Add dependencies across files and packages.
    cross_file_calls = find_cross_file_calls(root)

    for call in cross_file_calls:
        caller = call.caller
        target = call.target

        # Only connect symbols represented by
        # unique, unambiguous graph node IDs.
        if caller not in graph or target not in graph:
            continue

        if graph.has_edge(caller, target):
            lines = graph.edges[
                caller, target
            ]["call_lines"]

            if call.line not in lines:
                lines.append(call.line)
                lines.sort()
        else:
            graph.add_edge(
                caller,
                target,
                relationship="calls",
                confidence=call.confidence,
                call_lines=[call.line],
            )

    return graph
