import subprocess
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.api.routes import analysis as analysis_routes
from app.main import app

client = TestClient(app)

URL = "/api/v1/repositories/change-risk"


def git(root: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(root), *args],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def write_file(
    root: Path,
    name: str,
    content: str,
) -> None:
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


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


def create_repo(workspace: Path) -> Path:
    root = workspace / "demo-project"
    root.mkdir()

    git(root, "init", "-q")
    git(root, "config", "user.name", "CodeDNA Test")
    git(
        root,
        "config",
        "user.email",
        "codedna@example.test",
    )

    write_file(root, "app/__init__.py", "")
    write_file(root, "app/services/__init__.py", "")

    write_file(
        root,
        "app/services/users.py",
        "def get_user():\n    return 1\n",
    )

    write_file(
        root,
        "app/auth.py",
        (
            "from app.services.users import get_user\n\n"
            "def login():\n"
            "    return get_user()\n"
        ),
    )

    write_file(
        root,
        "main.py",
        (
            "from app.auth import login\n\n"
            "def start():\n"
            "    return login()\n"
        ),
    )

    return root


def commit(root: Path, message: str) -> str:
    git(root, "add", "-A")
    git(root, "commit", "-qm", message)
    return git(root, "rev-parse", "HEAD")


def request_risk(
    base: str,
    target: str,
    repository: str = "demo-project",
):
    return client.post(
        URL,
        json={
            "repository": repository,
            "base_revision": base,
            "target_revision": target,
        },
    )


def test_api_returns_explainable_risk(
    workspace: Path,
) -> None:
    root = create_repo(workspace)
    base = commit(root, "base")

    write_file(
        root,
        "app/services/users.py",
        "def get_user():\n    return 2\n",
    )

    target = commit(root, "change user")

    response = request_risk(base, target)

    assert response.status_code == 200

    data = response.json()

    assert data["changed_symbol_count"] == 1
    assert data["scored_count"] == 1
    assert data["unknown_count"] == 0
    assert data["highest_level"] == "medium"

    assert data["methodology"]

    item = data["items"][0]

    assert item["qualified_name"] == "get_user"
    assert item["score"] == 43
    assert item["level"] == "medium"

    assert item["direct_count"] == 1
    assert item["indirect_count"] == 1
    assert item["impacted_file_count"] == 2

    assert item["direct_callers"] == [
        "app/auth.py::login",
    ]

    assert item["indirect_callers"] == [
        "main.py::start",
    ]

    assert len(item["reasons"]) == 4


def test_api_same_commit_returns_empty_report(
    workspace: Path,
) -> None:
    root = create_repo(workspace)
    revision = commit(root, "initial")

    response = request_risk(
        revision,
        revision,
    )

    assert response.status_code == 200

    data = response.json()

    assert data["changed_symbol_count"] == 0
    assert data["items"] == []
    assert data["highest_level"] == "none"


def test_api_invalid_revision_returns_422(
    workspace: Path,
) -> None:
    root = create_repo(workspace)
    commit(root, "initial")

    response = request_risk(
        "INVALID_REVISION",
        "HEAD",
    )

    assert response.status_code == 422


def test_api_missing_repository_returns_404(
    workspace: Path,
) -> None:
    response = request_risk(
        "HEAD",
        "HEAD",
    )

    assert response.status_code == 404


def test_api_unavailable_workspace_returns_503(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        analysis_routes,
        "WORKSPACES_DIR",
        tmp_path / "missing-workspace",
    )

    response = request_risk(
        "HEAD",
        "HEAD",
    )

    assert response.status_code == 503
