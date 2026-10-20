from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.api.routes import analysis as analysis_routes
from app.main import app

client = TestClient(app)

ANALYSIS_URL = "/api/v1/repositories/analyze-python"


@pytest.fixture
def workspace(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> Path:
    workspace_dir = tmp_path / "workspaces"
    workspace_dir.mkdir()

    monkeypatch.setattr(
        analysis_routes,
        "WORKSPACES_DIR",
        workspace_dir,
    )

    return workspace_dir


def test_analyze_valid_python_file(
    workspace: Path,
) -> None:
    source_dir = workspace / "demo-project" / "src"
    source_dir.mkdir(parents=True)

    (source_dir / "service.py").write_text(
        "def helper(value: int) -> int:\n"
        "    return value + 1\n\n"
        "def process(value: int) -> int:\n"
        "    return helper(value)\n",
        encoding="utf-8",
    )

    response = client.post(
        ANALYSIS_URL,
        json={
            "repository": "demo-project",
            "file": "src/service.py",
        },
    )

    assert response.status_code == 200

    data = response.json()

    assert data["repository"] == "demo-project"
    assert data["file"] == "src/service.py"

    assert len(data["symbols"]) == 2
    assert len(data["calls"]) == 1
    assert len(data["resolutions"]) == 1

    assert data["symbols"][0]["name"] == "helper"
    assert data["symbols"][1]["name"] == "process"

    resolution = data["resolutions"][0]

    assert resolution["caller"] == "process"
    assert resolution["callee"] == "helper"
    assert resolution["target"] == "helper"
    assert resolution["status"] == "candidate"


def test_repository_not_found(
    workspace: Path,
) -> None:
    response = client.post(
        ANALYSIS_URL,
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
        ANALYSIS_URL,
        json={
            "repository": "demo-project",
            "file": "missing.py",
        },
    )

    assert response.status_code == 404
    assert response.json()["detail"] == (
        "Python file not found"
    )


def test_blocks_directory_traversal(
    workspace: Path,
) -> None:
    response = client.post(
        ANALYSIS_URL,
        json={
            "repository": "demo-project",
            "file": "../private.py",
        },
    )

    assert response.status_code == 422


def test_rejects_non_python_file(
    workspace: Path,
) -> None:
    response = client.post(
        ANALYSIS_URL,
        json={
            "repository": "demo-project",
            "file": "notes.txt",
        },
    )

    assert response.status_code == 422


def test_rejects_invalid_python_syntax(
    workspace: Path,
) -> None:
    repository = workspace / "demo-project"
    repository.mkdir()

    (repository / "broken.py").write_text(
        "def broken(:\n    pass\n",
        encoding="utf-8",
    )

    response = client.post(
        ANALYSIS_URL,
        json={
            "repository": "demo-project",
            "file": "broken.py",
        },
    )

    assert response.status_code == 422
    assert "Invalid Python syntax" in (
        response.json()["detail"]
    )


def test_rejects_file_symlink(
    workspace: Path,
    tmp_path: Path,
) -> None:
    repository = workspace / "demo-project"
    repository.mkdir()

    outside = tmp_path / "outside.py"
    outside.write_text(
        "secret = True\n",
        encoding="utf-8",
    )

    (repository / "linked.py").symlink_to(outside)

    response = client.post(
        ANALYSIS_URL,
        json={
            "repository": "demo-project",
            "file": "linked.py",
        },
    )

    assert response.status_code == 400
    assert response.json()["detail"] == (
        "File symlinks are not allowed"
    )


def test_rejects_directory_symlink(
    workspace: Path,
    tmp_path: Path,
) -> None:
    repository = workspace / "demo-project"
    repository.mkdir()

    outside_dir = tmp_path / "outside"
    outside_dir.mkdir()

    (outside_dir / "secret.py").write_text(
        "secret = True\n",
        encoding="utf-8",
    )

    (repository / "linked").symlink_to(
        outside_dir,
        target_is_directory=True,
    )

    response = client.post(
        ANALYSIS_URL,
        json={
            "repository": "demo-project",
            "file": "linked/secret.py",
        },
    )

    assert response.status_code == 400


def test_rejects_oversized_file(
    workspace: Path,
) -> None:
    repository = workspace / "demo-project"
    repository.mkdir()

    (repository / "large.py").write_bytes(
        b"#" * 1_000_001
    )

    response = client.post(
        ANALYSIS_URL,
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
        ANALYSIS_URL,
        json={
            "repository": "demo-project",
            "file": "main.py",
        },
    )

    assert response.status_code == 503
