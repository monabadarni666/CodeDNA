from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.api.routes import analysis as analysis_routes
from app.main import app

client = TestClient(app)

GRAPH_URL = "/api/v1/repositories/dependency-graph"


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


def create_python_file(
    workspace: Path,
    source: str,
    relative_path: str = "src/service.py",
) -> Path:
    file_path = (
        workspace / "demo-project" / relative_path
    )

    file_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    file_path.write_text(
        source,
        encoding="utf-8",
    )

    return file_path


def test_graph_with_indirect_impact(
    workspace: Path,
) -> None:
    source = (
        "def database():\n"
        "    return True\n\n"
        "def validate():\n"
        "    return database()\n\n"
        "def login():\n"
        "    return validate()\n"
    )

    create_python_file(workspace, source)

    response = client.post(
        GRAPH_URL,
        json={
            "repository": "demo-project",
            "file": "src/service.py",
            "changed_symbol": "database",
        },
    )

    assert response.status_code == 200

    data = response.json()

    assert data["node_count"] == 3
    assert data["edge_count"] == 2
    assert len(data["nodes"]) == 3
    assert len(data["edges"]) == 2

    prefix = "src/service.py::"

    actual_edges = {
        (edge["source"], edge["target"])
        for edge in data["edges"]
    }

    assert actual_edges == {
        (prefix + "validate", prefix + "database"),
        (prefix + "login", prefix + "validate"),
    }

    assert data["impact"] == {
        "changed_symbol": prefix + "database",
        "direct_callers": [prefix + "validate"],
        "indirect_callers": [prefix + "login"],
    }


def test_graph_without_changed_symbol(
    workspace: Path,
) -> None:
    create_python_file(
        workspace,
        "def helper():\n"
        "    return 1\n\n"
        "def process():\n"
        "    return helper()\n",
    )

    response = client.post(
        GRAPH_URL,
        json={
            "repository": "demo-project",
            "file": "src/service.py",
        },
    )

    assert response.status_code == 200

    data = response.json()

    assert data["node_count"] == 2
    assert data["edge_count"] == 1
    assert data["impact"] is None


def test_unknown_changed_symbol(
    workspace: Path,
) -> None:
    create_python_file(
        workspace,
        "def helper():\n"
        "    return True\n",
    )

    response = client.post(
        GRAPH_URL,
        json={
            "repository": "demo-project",
            "file": "src/service.py",
            "changed_symbol": "missing",
        },
    )

    assert response.status_code == 404
    assert response.json()["detail"] == (
        "Changed symbol not found in graph"
    )


def test_repository_not_found(
    workspace: Path,
) -> None:
    response = client.post(
        GRAPH_URL,
        json={
            "repository": "missing-project",
            "file": "main.py",
        },
    )

    assert response.status_code == 404
    assert response.json()["detail"] == (
        "Repository not found"
    )


def test_python_file_not_found(
    workspace: Path,
) -> None:
    (workspace / "demo-project").mkdir()

    response = client.post(
        GRAPH_URL,
        json={
            "repository": "demo-project",
            "file": "missing.py",
        },
    )

    assert response.status_code == 404
    assert response.json()["detail"] == (
        "Python file not found"
    )


def test_directory_traversal_blocked(
    workspace: Path,
) -> None:
    response = client.post(
        GRAPH_URL,
        json={
            "repository": "demo-project",
            "file": "../private.py",
        },
    )

    assert response.status_code == 422


def test_invalid_python_syntax(
    workspace: Path,
) -> None:
    create_python_file(
        workspace,
        "def broken(:\n    pass\n",
    )

    response = client.post(
        GRAPH_URL,
        json={
            "repository": "demo-project",
            "file": "src/service.py",
        },
    )

    assert response.status_code == 422

    assert "Invalid Python syntax" in (
        response.json()["detail"]
    )


def test_file_symlink_blocked(
    workspace: Path,
    tmp_path: Path,
) -> None:
    repository = workspace / "demo-project"
    repository.mkdir()

    outside = tmp_path / "secret.py"
    outside.write_text(
        "secret = True\n",
        encoding="utf-8",
    )

    (repository / "linked.py").symlink_to(outside)

    response = client.post(
        GRAPH_URL,
        json={
            "repository": "demo-project",
            "file": "linked.py",
        },
    )

    assert response.status_code == 400
    assert response.json()["detail"] == (
        "File symlinks are not allowed"
    )


def test_oversized_python_file(
    workspace: Path,
) -> None:
    file_path = (
        workspace / "demo-project" / "large.py"
    )

    file_path.parent.mkdir(parents=True)
    file_path.write_bytes(b"#" * 1_000_001)

    response = client.post(
        GRAPH_URL,
        json={
            "repository": "demo-project",
            "file": "large.py",
        },
    )

    assert response.status_code == 422

    assert "exceeds size limit" in (
        response.json()["detail"]
    )


def test_workspace_unavailable(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        analysis_routes,
        "WORKSPACES_DIR",
        tmp_path / "missing-workspace",
    )

    response = client.post(
        GRAPH_URL,
        json={
            "repository": "demo-project",
            "file": "main.py",
        },
    )

    assert response.status_code == 503
