from pathlib import Path

from fastapi.testclient import TestClient

from app.api.routes import repositories as repository_routes
from app.main import app

client = TestClient(app)

SCAN_URL = "/api/v1/repositories/scan"


def test_scan_valid_repository(
    tmp_path: Path,
    monkeypatch,
) -> None:
    workspace = tmp_path / "workspaces"
    repository = workspace / "demo-project"
    repository.mkdir(parents=True)

    (repository / "main.py").write_text(
        "print('Hello CodeDNA')",
        encoding="utf-8",
    )

    (repository / "App.tsx").write_text(
        "export const App = () => null;",
        encoding="utf-8",
    )

    monkeypatch.setattr(
        repository_routes,
        "WORKSPACES_DIR",
        workspace,
    )

    response = client.post(
        SCAN_URL,
        json={"repository": "demo-project"},
    )

    assert response.status_code == 200
    assert response.json() == {
        "repository": "demo-project",
        "total_source_files": 2,
        "languages": {
            "Python": 1,
            "TypeScript": 1,
        },
        "files": [
            "App.tsx",
            "main.py",
        ],
    }


def test_repository_not_found(
    tmp_path: Path,
    monkeypatch,
) -> None:
    workspace = tmp_path / "workspaces"
    workspace.mkdir()

    monkeypatch.setattr(
        repository_routes,
        "WORKSPACES_DIR",
        workspace,
    )

    response = client.post(
        SCAN_URL,
        json={"repository": "missing-project"},
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Repository not found"


def test_invalid_repository_name() -> None:
    response = client.post(
        SCAN_URL,
        json={"repository": "../private"},
    )

    assert response.status_code == 422


def test_repository_symlink_blocked(
    tmp_path: Path,
    monkeypatch,
) -> None:
    workspace = tmp_path / "workspaces"
    workspace.mkdir()

    outside = tmp_path / "outside"
    outside.mkdir()

    (workspace / "linked-project").symlink_to(
        outside,
        target_is_directory=True,
    )

    monkeypatch.setattr(
        repository_routes,
        "WORKSPACES_DIR",
        workspace,
    )

    response = client.post(
        SCAN_URL,
        json={"repository": "linked-project"},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == (
        "Repository symlinks are not allowed"
    )


def test_workspace_unavailable(
    tmp_path: Path,
    monkeypatch,
) -> None:
    missing_workspace = tmp_path / "missing-workspace"

    monkeypatch.setattr(
        repository_routes,
        "WORKSPACES_DIR",
        missing_workspace,
    )

    response = client.post(
        SCAN_URL,
        json={"repository": "demo-project"},
    )

    assert response.status_code == 503
