from pathlib import Path

import networkx as nx

from app.analysis.cross_file import (
    MAX_ROOT_FILES,
    find_cross_file_calls,
)
from app.analysis.dependency_graph import (
    build_dependency_graph,
)
from app.analysis.python_parser import analyze_python_file
from app.analysis.symbol_resolver import resolve_local_calls


def build_repository_dependency_graph(
    repository_root: str | Path,
) -> nx.DiGraph:
    """
    Build a repository-level dependency graph.

    Supported scope:
    - Root-level Python modules
    - Local candidate call relationships
    - Supported cross-file from-import calls

    Edges represent candidate relationships,
    not guaranteed runtime dependencies.
    """
    root = Path(repository_root).expanduser()

    if root.is_symlink() or not root.is_dir():
        raise ValueError(
            "Repository root must be a real directory"
        )

    python_files = sorted(
        path
        for path in root.iterdir()
        if path.suffix == ".py"
        and path.stem.isidentifier()
        and path.is_file()
        and not path.is_symlink()
    )

    if len(python_files) > MAX_ROOT_FILES:
        raise ValueError(
            "Repository exceeds supported module limit"
        )

    graph = nx.DiGraph(
        repository=str(root),
        file_count=len(python_files),
    )

    # Step 1: Build the graph for each Python file.
    for file_path in python_files:
        analysis = analyze_python_file(file_path)
        resolutions = resolve_local_calls(analysis)

        file_graph = build_dependency_graph(
            analysis=analysis,
            resolutions=resolutions,
            file_id=file_path.name,
        )

        graph.add_nodes_from(
            file_graph.nodes(data=True)
        )

        graph.add_edges_from(
            file_graph.edges(data=True)
        )

    # Step 2: Add dependencies between files.
    cross_file_calls = find_cross_file_calls(root)

    for call in cross_file_calls:
        caller = call.caller
        target = call.target

        # Both symbols must exist as unique graph nodes.
        # Ambiguous symbols are not linked.
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
