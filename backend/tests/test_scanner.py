from pathlib import Path

import pytest

from app.analysis.scanner import scan_repository


def test_scan_multiple_languages(tmp_path: Path) -> None:
    (tmp_path / "main.py").write_text(
        "print('hello')",
        encoding="utf-8",
    )

    src = tmp_path / "src"
    src.mkdir()

    (src / "App.tsx").write_text(
        "export default function App() {}",
        encoding="utf-8",
    )

    (src / "utils.ts").write_text(
        "export const value = 1;",
        encoding="utf-8",
    )

    (tmp_path / "README.md").write_text(
        "# Example",
        encoding="utf-8",
    )

    result = scan_repository(tmp_path)

    assert result.repository == tmp_path.name
    assert result.total_source_files == 3

    assert result.languages == {
        "Python": 1,
        "TypeScript": 2,
    }

    assert result.files == [
        "main.py",
        "src/App.tsx",
        "src/utils.ts",
    ]


def test_ignored_directories_and_symlinks(
    tmp_path: Path,
) -> None:
    (tmp_path / "main.py").write_text(
        "",
        encoding="utf-8",
    )

    node_modules = tmp_path / "node_modules"
    node_modules.mkdir()
    (node_modules / "hidden.js").write_text(
        "",
        encoding="utf-8",
    )

    venv = tmp_path / ".venv"
    venv.mkdir()
    (venv / "hidden.py").write_text(
        "",
        encoding="utf-8",
    )

    (tmp_path / "linked.py").symlink_to(
        tmp_path / "main.py"
    )

    (tmp_path / "linked_directory").symlink_to(
        node_modules,
        target_is_directory=True,
    )

    result = scan_repository(tmp_path)

    assert result.total_source_files == 1
    assert result.languages == {"Python": 1}
    assert result.files == ["main.py"]


def test_nonexistent_repository(tmp_path: Path) -> None:
    missing_path = tmp_path / "missing"

    with pytest.raises(
        ValueError,
        match="Repository directory not found",
    ):
        scan_repository(missing_path)


def test_case_insensitive_extensions(
    tmp_path: Path,
) -> None:
    (tmp_path / "Example.PY").write_text(
        "",
        encoding="utf-8",
    )

    (tmp_path / "Component.TSX").write_text(
        "",
        encoding="utf-8",
    )

    result = scan_repository(tmp_path)

    assert result.total_source_files == 2
    assert result.languages == {
        "Python": 1,
        "TypeScript": 1,
    }
