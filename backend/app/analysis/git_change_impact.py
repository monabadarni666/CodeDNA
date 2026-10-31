from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from tempfile import TemporaryDirectory

from app.analysis.dependency_graph import find_impact_candidates
from app.analysis.git_changed_symbols import (
    find_changed_symbols_between_commits,
)
from app.analysis.git_diff_analyzer import (
    GitDiffError,
    _git,
    _revision_hash,
)
from app.analysis.module_discovery import (
    IGNORED_DIRECTORIES,
    MAX_SUPPORTED_MODULES,
)
from app.analysis.repository_graph import (
    build_repository_dependency_graph,
)

MAX_GIT_SOURCE_BYTES = 1_000_000


@dataclass(frozen=True)
class SymbolImpact:
    old_path: str | None
    new_path: str | None
    qualified_name: str
    kind: str
    change_type: str
    graph_matched: bool
    direct_callers: list[str]
    indirect_callers: list[str]


@dataclass(frozen=True)
class GitImpactReport:
    base_commit: str
    target_commit: str
    changed_symbol_count: int
    changes: list[SymbolImpact]


def _materialize_git_python_tree(
    root: Path,
    commit: str,
    destination: Path,
) -> None:
    """
    Extract ordinary Python files into a temporary
    directory without checking out the repository.

    Source code is not executed.
    """
    listing = _git(
        root,
        "ls-tree",
        "-r",
        "-z",
        "--full-tree",
        commit,
    )

    blobs: list[tuple[PurePosixPath, str]] = []

    for entry in listing.split(b"\x00"):
        if not entry:
            continue

        metadata, separator, name_bytes = (
            entry.partition(b"\t")
        )

        parts = metadata.split()

        if not separator or len(parts) != 3:
            raise GitDiffError(
                "Invalid Git tree entry"
            )

        mode, object_type, object_id = parts

        if (
            mode not in (b"100644", b"100755")
            or object_type != b"blob"
        ):
            continue

        relative = PurePosixPath(
            name_bytes.decode(
                "utf-8",
                "surrogateescape",
            )
        )

        if (
            relative.is_absolute()
            or ".." in relative.parts
            or relative.suffix != ".py"
            or not relative.stem.isidentifier()
            or any(
                part in IGNORED_DIRECTORIES
                or part.startswith(".")
                or not part.isidentifier()
                for part in relative.parts[:-1]
            )
        ):
            continue

        blobs.append(
            (
                relative,
                object_id.decode("ascii"),
            )
        )

        if len(blobs) > MAX_SUPPORTED_MODULES:
            raise GitDiffError(
                "Repository exceeds supported module limit"
            )

    for relative, object_id in blobs:
        size_raw = _git(
            root,
            "cat-file",
            "-s",
            object_id,
        )

        try:
            size = int(size_raw)
        except ValueError as exc:
            raise GitDiffError(
                "Invalid Git object size"
            ) from exc

        if size > MAX_GIT_SOURCE_BYTES:
            raise GitDiffError(
                "Python source exceeds size limit: "
                f"{relative}"
            )

        data = _git(
            root,
            "cat-file",
            "blob",
            object_id,
        )

        if len(data) != size:
            raise GitDiffError(
                "Unexpected Git object size"
            )

        output_path = destination.joinpath(
            *relative.parts
        )

        output_path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        output_path.write_bytes(data)


def analyze_git_change_impact(
    repository_root: str | Path,
    base_revision: str,
    target_revision: str,
) -> GitImpactReport:
    root = Path(repository_root).expanduser()

    changed_symbols = (
        find_changed_symbols_between_commits(
            root,
            base_revision,
            target_revision,
        )
    )

    base = _revision_hash(
        root,
        base_revision,
    )

    target = _revision_hash(
        root,
        target_revision,
    )

    if not changed_symbols:
        return GitImpactReport(
            base_commit=base,
            target_commit=target,
            changed_symbol_count=0,
            changes=[],
        )

    with TemporaryDirectory(
        prefix="codedna-base-"
    ) as base_directory:
        with TemporaryDirectory(
            prefix="codedna-target-"
        ) as target_directory:
            base_path = Path(base_directory)
            target_path = Path(target_directory)

            _materialize_git_python_tree(
                root,
                base,
                base_path,
            )

            _materialize_git_python_tree(
                root,
                target,
                target_path,
            )

            base_graph = (
                build_repository_dependency_graph(
                    base_path
                )
            )

            target_graph = (
                build_repository_dependency_graph(
                    target_path
                )
            )

            impacts: list[SymbolImpact] = []

            for symbol in changed_symbols:
                direct: set[str] = set()
                indirect: set[str] = set()

                matched = False

                versions = []

                if symbol.change_type != "added":
                    versions.append(
                        (
                            base_graph,
                            symbol.old_path,
                        )
                    )

                if symbol.change_type != "deleted":
                    versions.append(
                        (
                            target_graph,
                            symbol.new_path,
                        )
                    )

                for graph, relative_path in versions:
                    if relative_path is None:
                        continue

                    node_id = (
                        f"{relative_path}::"
                        f"{symbol.qualified_name}"
                    )

                    if node_id not in graph:
                        continue

                    matched = True

                    impact = find_impact_candidates(
                        graph,
                        node_id,
                    )

                    direct.update(
                        impact.direct_callers
                    )

                    indirect.update(
                        impact.indirect_callers
                    )

                indirect.difference_update(
                    direct
                )

                impacts.append(
                    SymbolImpact(
                        old_path=symbol.old_path,
                        new_path=symbol.new_path,
                        qualified_name=(
                            symbol.qualified_name
                        ),
                        kind=symbol.kind,
                        change_type=(
                            symbol.change_type
                        ),
                        graph_matched=matched,
                        direct_callers=sorted(direct),
                        indirect_callers=sorted(
                            indirect
                        ),
                    )
                )

    return GitImpactReport(
        base_commit=base,
        target_commit=target,
        changed_symbol_count=len(impacts),
        changes=impacts,
    )
