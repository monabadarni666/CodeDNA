from pathlib import Path

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
        path = root / filename
        path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )
        path.write_text(
            source,
            encoding="utf-8",
        )

    return root


def test_impact_across_nested_packages(
    tmp_path: Path,
) -> None:
    root = create_repository(
        tmp_path,
        {
            "app/__init__.py": "",
            "app/services/__init__.py": "",
            "app/services/users.py": (
                "def get_user():\n"
                "    return {'id': 1}\n"
            ),
            "app/auth.py": (
                "from app.services.users import get_user\n\n\n"
                "def login():\n"
                "    return get_user()\n"
            ),
            "main.py": (
                "from app.auth import login\n\n\n"
                "def start():\n"
                "    return login()\n"
            ),
        },
    )

    graph = build_repository_dependency_graph(root)

    assert graph.graph["file_count"] == 5
    assert graph.number_of_nodes() == 3
    assert graph.number_of_edges() == 2

    assert graph.has_edge(
        "main.py::start",
        "app/auth.py::login",
    )

    assert graph.has_edge(
        "app/auth.py::login",
        "app/services/users.py::get_user",
    )

    impact = find_impact_candidates(
        graph,
        "app/services/users.py::get_user",
    )

    assert impact.direct_callers == [
        "app/auth.py::login",
    ]

    assert impact.indirect_callers == [
        "main.py::start",
    ]


def test_relative_import_between_package_modules(
    tmp_path: Path,
) -> None:
    root = create_repository(
        tmp_path,
        {
            "app/__init__.py": "",
            "app/users.py": (
                "def get_user():\n"
                "    return 1\n"
            ),
            "app/auth.py": (
                "from .users import get_user\n\n\n"
                "def login():\n"
                "    return get_user()\n"
            ),
        },
    )

    graph = build_repository_dependency_graph(root)

    assert graph.graph["file_count"] == 3
    assert graph.number_of_nodes() == 2
    assert graph.number_of_edges() == 1

    assert graph.has_edge(
        "app/auth.py::login",
        "app/users.py::get_user",
    )


def test_import_from_package_init(
    tmp_path: Path,
) -> None:
    root = create_repository(
        tmp_path,
        {
            "app/__init__.py": "",
            "app/services/__init__.py": (
                "def get_user():\n"
                "    return 1\n"
            ),
            "app/auth.py": (
                "from app.services import get_user\n\n\n"
                "def login():\n"
                "    return get_user()\n"
            ),
        },
    )

    graph = build_repository_dependency_graph(root)

    assert graph.number_of_nodes() == 2
    assert graph.number_of_edges() == 1

    assert graph.has_edge(
        "app/auth.py::login",
        "app/services/__init__.py::get_user",
    )
