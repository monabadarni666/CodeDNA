import subprocess
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.api.routes import analysis as analysis_routes
from app.main import app

client = TestClient(app)

URL = "/api/v1/repositories/change-impact"


def git(root: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(root), *args],
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.strip()


def write_file(
    root: Path,
    name: str,
    content: str,
) -> None:
    path = root / name
    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )
    path.write_text(
        content,
        encoding="utf-8",
    )


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

    return root


def commit(root: Path, message: str) -> str:
    git(root, "add", "-A")
    git(root, "commit", "-qm", message)
    return git(root, "rev-parse", "HEAD")


def create_chain(
    root: Path,
    users_source: str,
) -> None:
    write_file(
        root,
        "app/__init__.py",
        "",
    )

    write_file(
        root,
        "app/services/__init__.py",
        "",
    )

    write_file(
        root,
        "app/services/users.py",
        users_source,
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


def request_impact(
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


def test_modified_symbol_impacts_packages(
    workspace: Path,
) -> None:
    root = create_repo(workspace)

    create_chain(
        root,
        "def get_user():\n    return 1\n",
    )

    base = commit(root, "base")

    write_file(
        root,
        "app/services/users.py",
        "def get_user():\n    return 2\n",
    )

    target = commit(root, "change user")

    response = request_impact(base, target)

    assert response.status_code == 200

    data = response.json()

    assert data["changed_symbol_count"] == 1

    change = data["changes"][0]

    assert change["qualified_name"] == "get_user"
    assert change["change_type"] == "modified"
    assert change["graph_matched"] is True

    assert change["direct_callers"] == [
        "app/auth.py::login",
    ]

    assert change["indirect_callers"] == [
        "main.py::start",
    ]


def test_deleted_function_uses_base_graph(
    workspace: Path,
) -> None:
    root = create_repo(workspace)

    create_chain(
        root,
        "def get_user():\n    return 1\n",
    )

    base = commit(root, "base")

    (
        root / "app/services/users.py"
    ).unlink()

    target = commit(root, "delete user module")

    response = request_impact(base, target)

    assert response.status_code == 200

    change = response.json()["changes"][0]

    assert change["change_type"] == "deleted"
    assert change["graph_matched"] is True

    assert change["direct_callers"] == [
        "app/auth.py::login",
    ]

    assert change["indirect_callers"] == [
        "main.py::start",
    ]


def test_added_function_uses_target_graph(
    workspace: Path,
) -> None:
    root = create_repo(workspace)

    create_chain(
        root,
        "# no function yet\n",
    )

    base = commit(root, "base")

    write_file(
        root,
        "app/services/users.py",
        "def get_user():\n    return 1\n",
    )

    target = commit(root, "add user function")

    response = request_impact(base, target)

    assert response.status_code == 200

    change = response.json()["changes"][0]

    assert change["change_type"] == "added"
    assert change["graph_matched"] is True
    assert change["direct_callers"] == [
        "app/auth.py::login",
    ]


def test_uncommitted_worktree_is_ignored(
    workspace: Path,
) -> None:
    root = create_repo(workspace)

    create_chain(
        root,
        "def get_user():\n    return 1\n",
    )

    base = commit(root, "base")

    write_file(
        root,
        "app/services/users.py",
        "def get_user():\n    return 2\n",
    )

    target = commit(root, "change user")

    # This invalid working-tree source is uncommitted.
    write_file(
        root,
        "app/services/users.py",
        "def broken(:\n",
    )

    response = request_impact(base, target)

    assert response.status_code == 200
    assert (
        response.json()["changed_symbol_count"]
        == 1
    )


def test_same_commit_has_no_changes(
    workspace: Path,
) -> None:
    root = create_repo(workspace)

    write_file(
        root,
        "main.py",
        "def main():\n    return 1\n",
    )

    revision = commit(root, "initial")

    response = request_impact(
        revision,
        revision,
    )

    assert response.status_code == 200
    assert response.json()["changes"] == []


def test_non_python_change_is_ignored(
    workspace: Path,
) -> None:
    root = create_repo(workspace)

    write_file(root, "notes.txt", "before\n")
    base = commit(root, "base")

    write_file(root, "notes.txt", "after\n")
    target = commit(root, "notes changed")

    response = request_impact(base, target)

    assert response.status_code == 200
    assert response.json()["changes"] == []


def test_invalid_revision_returns_422(
    workspace: Path,
) -> None:
    root = create_repo(workspace)

    write_file(
        root,
        "main.py",
        "def main():\n    pass\n",
    )

    commit(root, "base")

    response = request_impact(
        "INVALID_REVISION",
        "HEAD",
    )

    assert response.status_code == 422


def test_missing_repository_returns_404(
    workspace: Path,
) -> None:
    response = request_impact(
        "HEAD",
        "HEAD",
    )

    assert response.status_code == 404


def test_workspace_unavailable_returns_503(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        analysis_routes,
        "WORKSPACES_DIR",
        tmp_path / "missing-workspace",
    )

    response = request_impact(
        "HEAD",
        "HEAD",
    )

    assert response.status_code == 503


def test_oversized_git_source_returns_422(
    workspace: Path,
) -> None:
    root = create_repo(workspace)

    write_file(
        root,
        "main.py",
        "def main():\n    return 1\n",
    )

    base = commit(root, "base")

    (
        root / "main.py"
    ).write_bytes(b"#" * 1_000_001)

    target = commit(root, "oversized source")

    response = request_impact(base, target)

    assert response.status_code == 422
