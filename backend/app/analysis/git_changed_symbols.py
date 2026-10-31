import io
import os
import tokenize
from dataclasses import dataclass
from pathlib import Path

from app.analysis.changed_symbols import compare_python_sources
from app.analysis.git_diff_analyzer import (
    GitDiffError,
    _git,
    _revision_hash,
    list_changed_files,
)

MAX_GIT_SOURCE_BYTES = 1_000_000


@dataclass(frozen=True)
class GitChangedSymbol:
    old_path: str | None
    new_path: str | None
    qualified_name: str
    kind: str
    change_type: str
    old_line: int | None
    new_line: int | None


def _read_python_at_commit(
    root: Path,
    commit_hash: str,
    path: str | None,
) -> str | None:
    if path is None or not path.endswith(".py"):
        return None

    # Read the Git tree, not the working directory.
    # Use literal paths to avoid Git pathspec expansion.
    listing = _git(
        root,
        "--literal-pathspecs",
        "ls-tree",
        "-r",
        "-z",
        "--full-tree",
        commit_hash,
        "--",
        path,
    )

    for entry in listing.split(b"\x00"):
        if not entry:
            continue

        metadata, separator, name = entry.partition(b"\t")

        if not separator or os.fsdecode(name) != path:
            continue

        parts = metadata.split()

        if len(parts) != 3:
            raise GitDiffError("Invalid Git tree entry")

        mode, object_type, object_id = parts

        # Only ordinary files are analyzed.
        # Git symlinks and submodules are excluded.
        if mode not in (b"100644", b"100755"):
            return None

        if object_type != b"blob":
            return None

        oid = object_id.decode("ascii")

        size = int(
            _git(root, "cat-file", "-s", oid).strip()
        )

        if size > MAX_GIT_SOURCE_BYTES:
            raise GitDiffError(
                f"Python source exceeds size limit: {path}"
            )

        content = _git(root, "cat-file", "blob", oid)

        try:
            encoding, _ = tokenize.detect_encoding(
                io.BytesIO(content).readline
            )
            return content.decode(encoding)
        except (SyntaxError, UnicodeError, LookupError) as exc:
            raise GitDiffError(
                f"Unable to decode Python source: {path}"
            ) from exc

    return None


def find_changed_symbols_between_commits(
    repository_root: str | Path,
    base_revision: str,
    target_revision: str,
) -> list[GitChangedSymbol]:
    root = Path(repository_root).expanduser()

    # This validates the repository and revisions,
    # and identifies added, modified, deleted
    # and renamed files.
    file_changes = list_changed_files(
        root,
        base_revision,
        target_revision,
    )

    base = _revision_hash(root, base_revision)
    target = _revision_hash(root, target_revision)

    results: list[GitChangedSymbol] = []

    for file_change in file_changes:
        old_source = _read_python_at_commit(
            root,
            base,
            file_change.old_path,
        )

        new_source = _read_python_at_commit(
            root,
            target,
            file_change.new_path,
        )

        if old_source is None and new_source is None:
            continue

        try:
            symbol_changes = compare_python_sources(
                old_source,
                new_source,
            )
        except ValueError as exc:
            raise GitDiffError(
                "Unable to compare Python symbols in "
                f"{file_change.new_path or file_change.old_path}"
            ) from exc

        for symbol in symbol_changes:
            results.append(
                GitChangedSymbol(
                    old_path=file_change.old_path,
                    new_path=file_change.new_path,
                    qualified_name=symbol.qualified_name,
                    kind=symbol.kind,
                    change_type=symbol.change_type,
                    old_line=symbol.old_line,
                    new_line=symbol.new_line,
                )
            )

    return sorted(
        results,
        key=lambda item: (
            item.new_path or item.old_path or "",
            item.qualified_name,
            item.change_type,
        ),
    )
