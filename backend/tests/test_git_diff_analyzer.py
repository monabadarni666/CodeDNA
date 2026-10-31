import subprocess
from pathlib import Path

import pytest

from app.analysis.git_diff_analyzer import (
    GitDiffError,
    list_changed_files,
)


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


def test_detects_file_change_types(
    tmp_path: Path,
) -> None:
    root = create_repository(tmp_path)

    (root / "keep.py").write_text("print(1)\n")
    (root / "remove.py").write_text("remove\n")
    (root / "before.py").write_text(
        "rename me unchanged\n"
    )

    base = commit(root, "base")

    (root / "keep.py").write_text("print(2)\n")
    (root / "remove.py").unlink()
    (root / "add.py").write_text("added\n")

    (root / "before.py").rename(
        root / "after.py"
    )

    target = commit(root, "target")

    changes = list_changed_files(
        root,
        base,
        target,
    )

    actual = {
        (
            change.change_type,
            change.old_path,
            change.new_path,
        )
        for change in changes
    }

    assert actual == {
        ("modified", "keep.py", "keep.py"),
        ("deleted", "remove.py", None),
        ("added", None, "add.py"),
        ("renamed", "before.py", "after.py"),
    }


def test_same_commit_has_no_changes(
    tmp_path: Path,
) -> None:
    root = create_repository(tmp_path)

    (root / "a.py").write_text("a\n")
    commit(root, "first")

    assert list_changed_files(
        root,
        "HEAD",
        "HEAD",
    ) == []


def test_invalid_revision_is_rejected(
    tmp_path: Path,
) -> None:
    root = create_repository(tmp_path)

    (root / "a.py").write_text("a\n")
    commit(root, "first")

    with pytest.raises(GitDiffError):
        list_changed_files(
            root,
            "NOT_A_COMMIT",
            "HEAD",
        )


def test_requires_git_repository_root(
    tmp_path: Path,
) -> None:
    root = create_repository(tmp_path)

    (root / "a.py").write_text("a\n")
    commit(root, "first")

    nested = root / "nested"
    nested.mkdir()

    with pytest.raises(
        GitDiffError,
        match="Git repository root",
    ):
        list_changed_files(
            nested,
            "HEAD",
            "HEAD",
        )


def test_symlinked_repository_is_rejected(
    tmp_path: Path,
) -> None:
    root = create_repository(tmp_path)

    (root / "a.py").write_text("a\n")
    commit(root, "first")

    link = tmp_path / "linked"

    link.symlink_to(
        root,
        target_is_directory=True,
    )

    with pytest.raises(GitDiffError):
        list_changed_files(
            link,
            "HEAD",
            "HEAD",
        )
