import subprocess
from pathlib import Path

import pytest

from app.analysis.git_changed_symbols import (
    find_changed_symbols_between_commits,
)
from app.analysis.git_diff_analyzer import GitDiffError


def git(root: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(root), *args],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def create_repository(tmp_path: Path) -> Path:
    root = tmp_path / "project"
    root.mkdir()

    git(root, "init", "-q")
    git(root, "config", "user.name", "CodeDNA Test")
    git(root, "config", "user.email", "test@example.test")

    return root


def commit(root: Path, message: str) -> str:
    git(root, "add", "-A")
    git(root, "commit", "-qm", message)
    return git(root, "rev-parse", "HEAD")


def test_modified_function(tmp_path: Path) -> None:
    root = create_repository(tmp_path)

    path = root / "users.py"
    path.write_text("def get_user():\n    return 1\n")

    base = commit(root, "base")

    path.write_text("def get_user():\n    return 2\n")
    target = commit(root, "modified")

    changes = find_changed_symbols_between_commits(
        root, base, target
    )

    assert len(changes) == 1
    assert changes[0].qualified_name == "get_user"
    assert changes[0].change_type == "modified"
    assert changes[0].old_path == "users.py"
    assert changes[0].new_path == "users.py"


def test_added_function(tmp_path: Path) -> None:
    root = create_repository(tmp_path)

    (root / "readme.txt").write_text("initial\n")
    base = commit(root, "base")

    (root / "users.py").write_text(
        "def create_user():\n    return True\n"
    )
    target = commit(root, "add function")

    changes = find_changed_symbols_between_commits(
        root, base, target
    )

    assert len(changes) == 1
    assert changes[0].qualified_name == "create_user"
    assert changes[0].change_type == "added"


def test_deleted_function(tmp_path: Path) -> None:
    root = create_repository(tmp_path)

    path = root / "users.py"
    path.write_text(
        "def delete_user():\n    return True\n"
    )
    base = commit(root, "base")

    path.unlink()
    target = commit(root, "delete function")

    changes = find_changed_symbols_between_commits(
        root, base, target
    )

    assert len(changes) == 1
    assert changes[0].qualified_name == "delete_user"
    assert changes[0].change_type == "deleted"


def test_unchanged_function_after_rename(
    tmp_path: Path,
) -> None:
    root = create_repository(tmp_path)

    path = root / "old.py"
    path.write_text("def helper():\n    return 1\n")
    base = commit(root, "base")

    path.rename(root / "new.py")
    target = commit(root, "rename")

    changes = find_changed_symbols_between_commits(
        root, base, target
    )

    assert changes == []


def test_non_python_changes_ignored(
    tmp_path: Path,
) -> None:
    root = create_repository(tmp_path)

    path = root / "notes.txt"
    path.write_text("before\n")
    base = commit(root, "base")

    path.write_text("after\n")
    target = commit(root, "update notes")

    assert find_changed_symbols_between_commits(
        root, base, target
    ) == []


def test_same_commit_has_no_changes(
    tmp_path: Path,
) -> None:
    root = create_repository(tmp_path)

    (root / "main.py").write_text(
        "def main():\n    return 1\n"
    )
    commit(root, "base")

    assert find_changed_symbols_between_commits(
        root, "HEAD", "HEAD"
    ) == []


def test_invalid_python_syntax(
    tmp_path: Path,
) -> None:
    root = create_repository(tmp_path)

    path = root / "main.py"
    path.write_text(
        "def main():\n    return 1\n"
    )
    base = commit(root, "base")

    path.write_text("def broken(:\n")
    target = commit(root, "invalid syntax")

    with pytest.raises(GitDiffError):
        find_changed_symbols_between_commits(
            root, base, target
        )
