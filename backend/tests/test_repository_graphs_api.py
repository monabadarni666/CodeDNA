from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.api.routes import analysis as analysis_routes
from app.main import app

client = TestClient(app)

GRAPH_URL = "/api/v1/repositories/graph"


@pytest.fixture
def workspace(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> Path:
    root = tmp_path / "workspaces"
    root.mkdir()

    monkeypatch.setattr(
        analysis_routes,
        "WORKSPACES_DIR",
        root,
    )

    return root


def create_repository(
    workspace: Path,
    files: dict[str, str],
) -> Path:
    root = workspace / "demo-project"
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


def request_graph(
    changed_symbol: str | None = None,
):
    payload = {"repository": "demo-project"}

    if changed_symbol is not None:
        payload["changed_symbol"] = changed_symbol

    return client.post(GRAPH_URL, json=payload)


def test_transitive_impact_across_three_files(
    workspace: Path,
) -> None:
    create_repository(
        workspace,
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

    response = request_graph(
        "database.py::get_user"
    )

    assert response.status_code == 200

    data = response.json()

    assert data["repository"] == "demo-project"
    assert data["file_count"] == 3
    assert data["node_count"] == 3
    assert data["edge_count"] == 2

    edges = {
        (edge["source"], edge["target"])
        for edge in data["edges"]
    }

    assert edges == {
        (
            "api.py::handle_request",
            "auth.py::login",
        ),
        (
            "auth.py::login",
            "database.py::get_user",
        ),
    }

    assert data["impact"] == {
        "changed_symbol": "database.py::get_user",
        "direct_callers": ["auth.py::login"],
        "indirect_callers": [
            "api.py::handle_request",
        ],
    }


def test_combines_local_and_cross_file_calls(
    workspace: Path,
) -> None:
    create_repository(
        workspace,
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

    response = request_graph(
        "database.py::get_user"
    )

    assert response.status_code == 200

    data = response.json()

    assert data["node_count"] == 3
    assert data["edge_count"] == 2

    assert data["impact"]["direct_callers"] == [
        "auth.py::validate",
    ]

    assert data["impact"]["indirect_callers"] == [
        "auth.py::login",
    ]


def test_graph_without_changed_symbol(
    workspace: Path,
) -> None:
    create_repository(
        workspace,
        {
            "service.py": (
                "def helper():\n"
                "    return 1\n\n\n"
                "def process():\n"
                "    return helper()\n"
            ),
        },
    )

    response = request_graph()

    assert response.status_code == 200

    data = response.json()

    assert data["file_count"] == 1
    assert data["node_count"] == 2
    assert data["edge_count"] == 1
    assert data["impact"] is None


def test_unknown_changed_symbol(
    workspace: Path,
) -> None:
    create_repository(
        workspace,
        {
            "main.py": (
                "def main():\n"
                "    return 1\n"
            ),
        },
    )

    response = request_graph(
        "main.py::missing"
    )

    assert response.status_code == 404
    assert response.json()["detail"] == (
        "Changed symbol not found in graph"
    )


def test_repository_not_found(
    workspace: Path,
) -> None:
    response = request_graph()

    assert response.status_code == 404


def test_empty_repository(
    workspace: Path,
) -> None:
    create_repository(workspace, {})

    response = request_graph()

    assert response.status_code == 200

    data = response.json()

    assert data["file_count"] == 0
    assert data["node_count"] == 0
    assert data["edge_count"] == 0
    assert data["nodes"] == []
    assert data["edges"] == []


def test_symlinked_file_is_ignored(
    workspace: Path,
    tmp_path: Path,
) -> None:
    root = create_repository(
        workspace,
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

    response = request_graph()

    assert response.status_code == 200

    data = response.json()

    assert data["file_count"] == 1
    assert data["node_count"] == 1
    assert data["edge_count"] == 0


def test_repository_module_limit(
    workspace: Path,
) -> None:
    files = {
        f"module_{index}.py": (
            "def example():\n"
            "    return 1\n"
        )
        for index in range(101)
    }

    create_repository(workspace, files)

    response = request_graph()

    assert response.status_code == 422

    assert "module limit" in (
        response.json()["detail"]
    )


def test_oversized_python_file(
    workspace: Path,
) -> None:
    root = create_repository(workspace, {})

    (root / "large.py").write_bytes(
        b"#" * 1_000_001
    )

    response = request_graph()

    assert response.status_code == 422


def test_workspace_unavailable(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        analysis_routes,
        "WORKSPACES_DIR",
        tmp_path / "missing-workspace",
    )

    response = request_graph()

    assert response.status_code == 503
