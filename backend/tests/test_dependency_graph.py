from pathlib import Path

import pytest

from app.analysis.dependency_graph import (
    build_dependency_graph,
    find_impact_candidates,
)
from app.analysis.python_parser import analyze_python_file
from app.analysis.symbol_resolver import resolve_local_calls

FILE_ID = "example.py"


def build_graph_from_source(
    tmp_path: Path,
    source: str,
):
    file_path = tmp_path / FILE_ID
    file_path.write_text(source, encoding="utf-8")

    analysis = analyze_python_file(file_path)
    resolutions = resolve_local_calls(analysis)

    return build_dependency_graph(
        analysis,
        resolutions,
        file_id=FILE_ID,
    )


def node_id(name: str) -> str:
    return f"{FILE_ID}::{name}"


def test_graph_construction(tmp_path: Path) -> None:
    source = """
def helper():
    return 42

def process():
    return helper()
"""

    graph = build_graph_from_source(tmp_path, source)

    assert graph.number_of_nodes() == 2
    assert graph.number_of_edges() == 1

    assert graph.has_node(node_id("helper"))
    assert graph.has_node(node_id("process"))

    assert graph.has_edge(
        node_id("process"),
        node_id("helper"),
    )

    edge = graph.edges[
        node_id("process"),
        node_id("helper"),
    ]

    assert edge["relationship"] == "calls"
    assert edge["confidence"] == "candidate"
    assert edge["call_lines"] == [6]


def test_direct_impact(tmp_path: Path) -> None:
    source = """
def helper():
    return 1

def first():
    return helper()

def second():
    return helper()
"""

    graph = build_graph_from_source(tmp_path, source)

    impact = find_impact_candidates(
        graph,
        node_id("helper"),
    )

    assert impact.direct_callers == [
        node_id("first"),
        node_id("second"),
    ]

    assert impact.indirect_callers == []


def test_indirect_impact(tmp_path: Path) -> None:
    source = """
def database():
    return True

def validate():
    return database()

def login():
    return validate()
"""

    graph = build_graph_from_source(tmp_path, source)

    impact = find_impact_candidates(
        graph,
        node_id("database"),
    )

    assert impact.direct_callers == [
        node_id("validate")
    ]

    assert impact.indirect_callers == [
        node_id("login")
    ]


def test_cyclic_dependencies(tmp_path: Path) -> None:
    source = """
def first():
    return second()

def second():
    return first()

def entry():
    return first()
"""

    graph = build_graph_from_source(tmp_path, source)

    assert graph.number_of_nodes() == 3
    assert graph.number_of_edges() == 3

    impact = find_impact_candidates(
        graph,
        node_id("second"),
    )

    assert impact.direct_callers == [
        node_id("first")
    ]

    assert impact.indirect_callers == [
        node_id("entry")
    ]

    assert node_id("second") not in (
        impact.direct_callers
        + impact.indirect_callers
    )


def test_repeated_calls_share_one_edge(
    tmp_path: Path,
) -> None:
    source = """
def helper():
    return 1

def process():
    helper()
    return helper()
"""

    graph = build_graph_from_source(tmp_path, source)

    assert graph.number_of_edges() == 1

    edge = graph.edges[
        node_id("process"),
        node_id("helper"),
    ]

    assert edge["call_lines"] == [6, 7]


def test_unresolved_calls_do_not_create_edges(
    tmp_path: Path,
) -> None:
    source = """
import os

def process():
    print("hello")
    return os.getenv("NAME")
"""

    graph = build_graph_from_source(tmp_path, source)

    assert graph.number_of_nodes() == 1
    assert graph.number_of_edges() == 0


def test_duplicate_definitions_and_unknown_node(
    tmp_path: Path,
) -> None:
    source = """
def helper():
    return 1

def helper():
    return 2

def process():
    return helper()
"""

    graph = build_graph_from_source(tmp_path, source)

    assert graph.number_of_nodes() == 3
    assert graph.number_of_edges() == 0

    helper_nodes = [
        node
        for node, data in graph.nodes(data=True)
        if data["qualified_name"] == "helper"
    ]

    assert len(helper_nodes) == 2
    assert len(set(helper_nodes)) == 2

    with pytest.raises(
        ValueError,
        match="Unknown graph symbol",
    ):
        find_impact_candidates(
            graph,
            node_id("missing"),
        )
