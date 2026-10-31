from pathlib import Path

import pytest

from app.analysis.module_discovery import (
    MAX_SUPPORTED_MODULES,
    discover_python_modules,
)


def create_file(
    root: Path,
    relative_path: str,
    content: str = "",
) -> Path:
    path = root / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def test_discovers_root_modules_and_packages(
    tmp_path: Path,
) -> None:
    create_file(tmp_path, "main.py")
    create_file(tmp_path, "__init__.py")
    create_file(tmp_path, "app/__init__.py")
    create_file(tmp_path, "app/auth.py")

    modules = discover_python_modules(tmp_path)

    assert {
        module.module_name
        for module in modules
    } == {"main", "app", "app.auth"}

    assert {
        module.module_name
        for module in modules
        if module.is_package
    } == {"app"}


def test_discovers_nested_packages(
    tmp_path: Path,
) -> None:
    create_file(tmp_path, "app/__init__.py")
    create_file(tmp_path, "app/services/__init__.py")
    create_file(tmp_path, "app/services/user.py")

    modules = discover_python_modules(tmp_path)

    by_name = {
        module.module_name: module
        for module in modules
    }

    assert "app.services.user" in by_name
    assert (
        by_name["app.services.user"].relative_path
        == "app/services/user.py"
    )
    assert by_name["app.services"].is_package


def test_skips_directories_without_init(
    tmp_path: Path,
) -> None:
    create_file(tmp_path, "main.py")
    create_file(tmp_path, "loose/helper.py")

    modules = discover_python_modules(tmp_path)

    assert [
        module.module_name
        for module in modules
    ] == ["main"]


def test_ignores_symlinked_files_and_directories(
    tmp_path: Path,
) -> None:
    root = tmp_path / "repository"
    root.mkdir()

    outside = tmp_path / "outside"
    outside.mkdir()

    target = create_file(outside, "secret.py")
    create_file(outside, "pkg/__init__.py")
    create_file(outside, "pkg/service.py")

    (root / "linked.py").symlink_to(target)

    (root / "linked_pkg").symlink_to(
        outside / "pkg",
        target_is_directory=True,
    )

    assert discover_python_modules(root) == []


def test_skips_ignored_directories(
    tmp_path: Path,
) -> None:
    create_file(tmp_path, ".venv/__init__.py")
    create_file(tmp_path, "node_modules/__init__.py")
    create_file(tmp_path, "__pycache__/__init__.py")
    create_file(tmp_path, "main.py")

    modules = discover_python_modules(tmp_path)

    assert len(modules) == 1
    assert modules[0].module_name == "main"


def test_rejects_ambiguous_module_names(
    tmp_path: Path,
) -> None:
    create_file(tmp_path, "service.py")
    create_file(tmp_path, "service/__init__.py")

    with pytest.raises(
        ValueError,
        match="Ambiguous Python module",
    ):
        discover_python_modules(tmp_path)


def test_enforces_module_limit(
    tmp_path: Path,
) -> None:
    for index in range(MAX_SUPPORTED_MODULES + 1):
        create_file(
            tmp_path,
            f"module_{index}.py",
        )

    with pytest.raises(
        ValueError,
        match="supported module limit",
    ):
        discover_python_modules(tmp_path)


def test_rejects_missing_and_symlinked_roots(
    tmp_path: Path,
) -> None:
    missing = tmp_path / "missing"

    with pytest.raises(ValueError):
        discover_python_modules(missing)

    real_root = tmp_path / "real"
    real_root.mkdir()

    linked_root = tmp_path / "linked"
    linked_root.symlink_to(
        real_root,
        target_is_directory=True,
    )

    with pytest.raises(ValueError):
        discover_python_modules(linked_root)
