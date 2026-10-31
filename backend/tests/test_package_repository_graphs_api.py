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
) -> None:
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


def request_graph(changed_symbol: str):
    return client.post(
        GRAPH_URL,
        json={
            "repository": "demo-project",
            "changed_symbol": changed_symbol,
        },
    )


def test_api_impact_across_nested_packages(
    workspace: Path,
) -> None:
    create_repository(
        workspace,
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

    response = request_graph(
        "app/services/users.py::get_user"
    )

    assert response.status_code == 200

    data = response.json()

    assert data["file_count"] == 5
    assert data["node_count"] == 3
    assert data["edge_count"] == 2

    edges = {
        (edge["source"], edge["target"])
        for edge in data["edges"]
    }

    assert edges == {
        (
            "main.py::start",
            "app/auth.py::login",
        ),
        (
            "app/auth.py::login",
            "app/services/users.py::get_user",
        ),
    }

    assert data["impact"] == {
        "changed_symbol": (
            "app/services/users.py::get_user"
        ),
        "direct_callers": [
            "app/auth.py::login",
        ],
        "indirect_callers": [
            "main.py::start",
        ],
    }


def test_api_relative_import_with_alias(
    workspace: Path,
) -> None:
    create_repository(
        workspace,
        {
            "app/__init__.py": "",
            "app/users.py": (
                "def get_user():\n"
                "    return 1\n"
            ),
            "app/auth.py": (
                "from .users import get_user as fetch\n\n\n"
                "def login():\n"
                "    return fetch()\n"
            ),
        },
    )

    response = request_graph(
        "app/users.py::get_user"
    )

    assert response.status_code == 200

    data = response.json()

    assert data["file_count"] == 3
    assert data["node_count"] == 2
    assert data["edge_count"] == 1

    assert data["impact"]["direct_callers"] == [
        "app/auth.py::login",
    ]

    assert data["impact"]["indirect_callers"] == []


def test_api_import_from_package_init(
    workspace: Path,
) -> None:
    create_repository(
        workspace,
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

    response = request_graph(
        "app/services/__init__.py::get_user"
    )

    assert response.status_code == 200

    data = response.json()

    assert data["file_count"] == 3
    assert data["node_count"] == 2
    assert data["edge_count"] == 1

    assert data["impact"]["direct_callers"] == [
        "app/auth.py::login",
    ]
