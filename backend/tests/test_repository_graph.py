from pathlib import Path

import pytest

from app.analysis.cross_file import MAX_ROOT_FILES
from app.analysis.dependency_graph import find_impact_candidates
from app.analysis.repository_graph import (
    build_repository_dependency_graph,
)


def create_repository(
    tmp_path: Path,
    files: dict[str, str],
) -> Path:
    root = tmp_path / "repository"
    root.mkdir()

    for filename, source in files.items():
        (root / filename).write_text(
            source,
            encoding="utf-8",
        )

    return root


def test_transitive_impact_across_three_files(
    tmp_path: Path,
) -> None:
    root = create_repository(
        tmp_path,
        {
            "database.py": (
                "def get_user():\n"
                "    return {'id': 1}\n"
            ),
            "auth.py": (
                "from database import get_user\n\n\n"
                "def login():\n"
                "    return get_user()\n"
            ),
            "api.py": (
                "from auth import login\n\n\n"
                "def handle_request():\n"
                "    return login()\n"
            ),
        },
    )

    graph = build_repository_dependency_graph(root)

    assert graph.graph["file_count"] == 3
    assert graph.number_of_nodes() == 3
    assert graph.number_of_edges() == 2

    assert graph.has_edge(
        "api.py::handle_request",
        "auth.py::login",
    )

    assert graph.has_edge(
        "auth.py::login",
        "database.py::get_user",
    )

    impact = find_impact_candidates(
        graph,
        "database.py::get_user",
    )

    assert impact.direct_callers == [
        "auth.py::login",
    ]

    assert impact.indirect_callers == [
        "api.py::handle_request",
    ]


def test_combines_local_and_cross_file_edges(
    tmp_path: Path,
) -> None:
    root = create_repository(
        tmp_path,
        {
            "database.py": (
                "def get_user():\n"
                "    return 1\n"
            ),
            "auth.py": (
                "from database import get_user\n\n\n"
                "def validate():\n"
                "    return get_user()\n\n\n"
                "def login():\n"
                "    return validate()\n"
            ),
        },
    )

    graph = build_repository_dependency_graph(root)

    assert graph.number_of_nodes() == 3
    assert graph.number_of_edges() == 2

    assert graph.has_edge(
        "auth.py::login",
        "auth.py::validate",
    )

    assert graph.has_edge(
        "auth.py::validate",
        "database.py::get_user",
    )

    impact = find_impact_candidates(
        graph,
        "database.py::get_user",
    )

    assert impact.direct_callers == [
        "auth.py::validate",
    ]

    assert impact.indirect_callers == [
        "auth.py::login",
    ]


def test_cross_file_import_alias(
    tmp_path: Path,
) -> None:
    root = create_repository(
        tmp_path,
        {
            "database.py": (
                "def get_user():\n"
                "    return 1\n"
            ),
            "auth.py": (
                "from database import get_user as fetch\n\n\n"
                "def login():\n"
                "    return fetch()\n"
            ),
        },
    )

    graph = build_repository_dependency_graph(root)

    assert graph.has_edge(
        "auth.py::login",
        "database.py::get_user",
    )

    assert graph.edges[
        "auth.py::login",
        "database.py::get_user",
    ]["confidence"] == "candidate"


def test_repeated_calls_share_one_edge(
    tmp_path: Path,
) -> None:
    root = create_repository(
        tmp_path,
        {
            "database.py": (
                "def get_user():\n"
                "    return 1\n"
            ),
            "auth.py": (
                "from database import get_user\n\n\n"
                "def login():\n"
                "    first = get_user()\n"
                "    return get_user()\n"
            ),
        },
    )

    graph = build_repository_dependency_graph(root)

    assert graph.number_of_edges() == 1

    edge = graph.edges[
        "auth.py::login",
        "database.py::get_user",
    ]

    assert edge["call_lines"] == [5, 6]


def test_duplicate_target_is_not_linked(
    tmp_path: Path,
) -> None:
    root = create_repository(
        tmp_path,
        {
            "database.py": (
                "def get_user():\n"
                "    return 1\n\n\n"
                "def get_user():\n"
                "    return 2\n"
            ),
            "auth.py": (
                "from database import get_user\n\n\n"
                "def login():\n"
                "    return get_user()\n"
            ),
        },
    )

    graph = build_repository_dependency_graph(root)

    assert graph.number_of_nodes() == 3
    assert graph.number_of_edges() == 0


def test_shadowed_import_is_not_linked(
    tmp_path: Path,
) -> None:
    root = create_repository(
        tmp_path,
        {
            "database.py": (
                "def get_user():\n"
                "    return 1\n"
            ),
            "auth.py": (
                "from database import get_user\n\n\n"
                "def login(get_user):\n"
                "    return get_user()\n"
            ),
        },
    )

    graph = build_repository_dependency_graph(root)

    assert graph.number_of_nodes() == 2
    assert graph.number_of_edges() == 0


def test_symlinked_python_file_is_ignored(
    tmp_path: Path,
) -> None:
    root = create_repository(
        tmp_path,
        {
            "auth.py": (
                "from database import get_user\n\n\n"
                "def login():\n"
                "    return get_user()\n"
            ),
        },
    )

    outside = tmp_path / "outside.py"
    outside.write_text(
        "def get_user():\n"
        "    return 1\n",
        encoding="utf-8",
    )

    (root / "database.py").symlink_to(outside)

    graph = build_repository_dependency_graph(root)

    assert graph.graph["file_count"] == 1
    assert graph.number_of_nodes() == 1
    assert graph.number_of_edges() == 0


def test_empty_repository(
    tmp_path: Path,
) -> None:
    root = create_repository(tmp_path, {})

    graph = build_repository_dependency_graph(root)

    assert graph.graph["file_count"] == 0
    assert graph.number_of_nodes() == 0
    assert graph.number_of_edges() == 0


def test_module_limit_is_enforced(
    tmp_path: Path,
) -> None:
    files = {
        f"module_{index}.py": "def example():\n    pass\n"
        for index in range(MAX_ROOT_FILES + 1)
    }

    root = create_repository(tmp_path, files)

    with pytest.raises(
        ValueError,
        match="Repository exceeds supported module limit",
    ):
        build_repository_dependency_graph(root)


def test_symlinked_repository_is_rejected(
    tmp_path: Path,
) -> None:
    root = create_repository(
        tmp_path,
        {
            "main.py": (
                "def main():\n"
                "    return 1\n"
            ),
        },
    )

    link = tmp_path / "linked-repository"
    link.symlink_to(
        root,
        target_is_directory=True,
    )

    with pytest.raises(
        ValueError,
        match="Repository root must be a real directory",
    ):
        build_repository_dependency_graph(link)
