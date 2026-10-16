import os
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

LANGUAGE_EXTENSIONS = {
    ".py": "Python",
    ".js": "JavaScript",
    ".jsx": "JavaScript",
    ".ts": "TypeScript",
    ".tsx": "TypeScript",
    ".java": "Java",
    ".c": "C",
    ".cpp": "C++",
    ".cc": "C++",
    ".h": "C/C++",
    ".hpp": "C++",
    ".go": "Go",
    ".rs": "Rust",
    ".cs": "C#",
    ".rb": "Ruby",
}

IGNORED_DIRECTORIES = {
    ".git",
    ".venv",
    "venv",
    "node_modules",
    "__pycache__",
    ".pytest_cache",
    ".ruff_cache",
    "dist",
    "build",
}


@dataclass
class RepositoryScan:
    repository: str
    total_source_files: int
    languages: dict[str, int]
    files: list[str]


def scan_repository(path: str | Path) -> RepositoryScan:
    root = Path(path).expanduser().resolve()

    if not root.is_dir():
        raise ValueError(
            f"Repository directory not found: {root}"
        )

    source_files = []
    language_counts = Counter()

    for current_dir, directories, filenames in os.walk(
        root,
        followlinks=False,
    ):
        current_path = Path(current_dir)

        directories[:] = sorted(
            directory
            for directory in directories
            if directory not in IGNORED_DIRECTORIES
            and not (current_path / directory).is_symlink()
        )

        for filename in sorted(filenames):
            file_path = current_path / filename

            if file_path.is_symlink():
                continue

            language = LANGUAGE_EXTENSIONS.get(
                file_path.suffix.lower()
            )

            if language is None:
                continue

            relative_path = file_path.relative_to(root)

            source_files.append(relative_path.as_posix())
            language_counts[language] += 1

    return RepositoryScan(
        repository=root.name,
        total_source_files=len(source_files),
        languages=dict(sorted(language_counts.items())),
        files=sorted(source_files),
    )
