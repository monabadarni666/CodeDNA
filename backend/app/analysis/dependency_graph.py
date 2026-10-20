from collections import Counter
from dataclasses import dataclass

import networkx as nx

from app.analysis.python_parser import PythonFileAnalysis
from app.analysis.symbol_resolver import CallResolution


@dataclass(frozen=True)
class ImpactCandidates:
    changed_symbol: str
    direct_callers: list[str]
    indirect_callers: list[str]


def build_dependency_graph(
    analysis: PythonFileAnalysis,
    resolutions: list[CallResolution],
    file_id: str,
) -> nx.DiGraph:
    """
    Build a candidate call graph for one Python file.

    Edge direction: caller -> callee.
    Only uniquely identified candidate calls become edges.
    """
    graph = nx.DiGraph(file=file_id)

    symbol_counts = Counter(
        symbol.qualified_name
        for symbol in analysis.symbols
    )

    # Create nodes for source-code symbols.
    for symbol in analysis.symbols:
        base_id = (
            f"{file_id}::{symbol.qualified_name}"
        )

        if symbol_counts[symbol.qualified_name] == 1:
            node_id = base_id
        else:
            node_id = (
                f"{base_id}@line:{symbol.line}"
            )

        graph.add_node(
            node_id,
            name=symbol.name,
            qualified_name=symbol.qualified_name,
            kind=symbol.kind,
            file=file_id,
            line=symbol.line,
            end_line=symbol.end_line,
        )

    # Create edges from resolved candidate calls.
    for resolution in resolutions:
        if (
            resolution.status != "candidate"
            or resolution.caller is None
            or resolution.target is None
        ):
            continue

        # Avoid connecting duplicate symbol definitions.
        if (
            symbol_counts[resolution.caller] != 1
            or symbol_counts[resolution.target] != 1
        ):
            continue

        caller_id = (
            f"{file_id}::{resolution.caller}"
        )

        target_id = (
            f"{file_id}::{resolution.target}"
        )

        if (
            caller_id not in graph
            or target_id not in graph
        ):
            continue

        if graph.has_edge(caller_id, target_id):
            lines = graph.edges[
                caller_id, target_id
            ]["call_lines"]

            if resolution.line not in lines:
                lines.append(resolution.line)
                lines.sort()

        else:
            graph.add_edge(
                caller_id,
                target_id,
                relationship="calls",
                confidence="candidate",
                call_lines=[resolution.line],
            )

    return graph


def find_impact_candidates(
    graph: nx.DiGraph,
    changed_symbol: str,
) -> ImpactCandidates:
    """
    Find functions that may depend on a changed symbol.

    This is graph reachability, not proof of a runtime impact.
    """
    if changed_symbol not in graph:
        raise ValueError(
            f"Unknown graph symbol: {changed_symbol}"
        )

    direct = set(
        graph.predecessors(changed_symbol)
    )

    all_callers = nx.ancestors(
        graph,
        changed_symbol,
    )

    direct.discard(changed_symbol)
    all_callers.discard(changed_symbol)

    return ImpactCandidates(
        changed_symbol=changed_symbol,
        direct_callers=sorted(direct),
        indirect_callers=sorted(
            all_callers - direct
        ),
    )
