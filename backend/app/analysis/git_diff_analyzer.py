import os
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

ChangeType = Literal[
    "added",
    "modified",
    "deleted",
    "renamed",
    "copied",
    "type_changed",
]


class GitDiffError(ValueError):
    """Git repository or diff cannot be analyzed."""


@dataclass(frozen=True)
class GitFileChange:
    change_type: ChangeType
    old_path: str | None
    new_path: str | None


def _git(root: Path, *args: str) -> bytes:
    try:
        result = subprocess.run(
            [
                "git",
                "-C",
                str(root),
                "-c",
                "core.fsmonitor=false",
                *args,
            ],
            capture_output=True,
            check=False,
            timeout=15,
            env={
                **os.environ,
                "GIT_OPTIONAL_LOCKS": "0",
                "GIT_TERMINAL_PROMPT": "0",
            },
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise GitDiffError(
            "Unable to run Git command"
        ) from exc

    if result.returncode:
        message = result.stderr.decode(
            "utf-8",
            errors="replace",
        ).strip()

        raise GitDiffError(
            f"Git command failed: {message[:250]}"
        )

    return result.stdout


def _revision_hash(
    root: Path,
    revision: str,
) -> str:
    if (
        not revision
        or len(revision) > 128
        or "\x00" in revision
        or "\n" in revision
    ):
        raise GitDiffError("Invalid Git revision")

    output = _git(
        root,
        "rev-parse",
        "--verify",
        "--end-of-options",
        f"{revision}^{{commit}}",
    )

    return output.decode("ascii").strip()


def list_changed_files(
    repository_root: str | Path,
    base_revision: str,
    target_revision: str,
) -> list[GitFileChange]:
    root = Path(repository_root).expanduser()

    if root.is_symlink() or not root.is_dir():
        raise GitDiffError(
            "Repository root must be a real directory"
        )

    root = root.resolve()

    top_level = Path(
        _git(
            root,
            "rev-parse",
            "--show-toplevel",
        ).decode("utf-8").strip()
    ).resolve()

    if top_level != root:
        raise GitDiffError(
            "Path must be the Git repository root"
        )

    base = _revision_hash(root, base_revision)
    target = _revision_hash(root, target_revision)

    raw = _git(
        root,
        "diff",
        "--no-ext-diff",
        "--no-textconv",
        "--find-renames",
        "--name-status",
        "-z",
        base,
        target,
        "--",
    )

    fields = raw.decode(
        "utf-8",
        errors="surrogateescape",
    ).split("\x00")

    if fields[-1] != "":
        raise GitDiffError(
            "Unexpected Git diff output"
        )

    fields.pop()

    kinds: dict[str, ChangeType] = {
        "A": "added",
        "M": "modified",
        "D": "deleted",
        "R": "renamed",
        "C": "copied",
        "T": "type_changed",
    }

    changes: list[GitFileChange] = []
    index = 0

    while index < len(fields):
        code = fields[index]
        index += 1

        kind = kinds.get(code[:1])

        if kind is None:
            raise GitDiffError(
                f"Unsupported Git change status: {code}"
            )

        path_count = (
            2 if code.startswith(("R", "C")) else 1
        )

        if index + path_count > len(fields):
            raise GitDiffError(
                "Incomplete Git diff output"
            )

        paths = fields[
            index:index + path_count
        ]

        index += path_count

        if path_count == 2:
            old_path, new_path = paths

        elif kind == "added":
            old_path, new_path = None, paths[0]

        elif kind == "deleted":
            old_path, new_path = paths[0], None

        else:
            old_path = new_path = paths[0]

        changes.append(
            GitFileChange(
                change_type=kind,
                old_path=old_path,
                new_path=new_path,
            )
        )

    return changes
