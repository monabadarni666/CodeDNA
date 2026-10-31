from dataclasses import dataclass
from pathlib import Path

MAX_SUPPORTED_MODULES = 100

IGNORED_DIRECTORIES = {
    ".git",
    ".venv",
    "venv",
    "__pycache__",
    "node_modules",
    "build",
    "dist",
    "workspaces",
}


@dataclass(frozen=True)
class PythonModule:
    module_name: str
    relative_path: str
    path: Path
    is_package: bool


def discover_python_modules(
    repository_root: str | Path,
) -> list[PythonModule]:
    """
    Discover root-level Python modules and regular
    Python packages containing __init__.py.

    Namespace packages are not yet supported.
    Symbolic links are never followed.
    """
    root = Path(repository_root).expanduser()

    if root.is_symlink() or not root.is_dir():
        raise ValueError(
            "Repository root must be a real directory"
        )

    modules: list[PythonModule] = []
    registered: set[str] = set()

    def add_module(
        path: Path,
        module_name: str,
        is_package: bool,
    ) -> None:
        if module_name in registered:
            raise ValueError(
                f"Ambiguous Python module: {module_name}"
            )

        registered.add(module_name)

        modules.append(
            PythonModule(
                module_name=module_name,
                relative_path=path.relative_to(
                    root
                ).as_posix(),
                path=path,
                is_package=is_package,
            )
        )

        if len(modules) > MAX_SUPPORTED_MODULES:
            raise ValueError(
                "Repository exceeds supported module limit"
            )

    def scan_directory(
        directory: Path,
        package_parts: tuple[str, ...],
    ) -> None:
        if package_parts:
            init_file = directory / "__init__.py"

            if (
                init_file.is_symlink()
                or not init_file.is_file()
            ):
                return

            add_module(
                init_file,
                ".".join(package_parts),
                is_package=True,
            )

        entries = sorted(
            directory.iterdir(),
            key=lambda entry: entry.name,
        )

        for entry in entries:
            if entry.is_symlink():
                continue

            if entry.is_file():
                if (
                    entry.suffix != ".py"
                    or entry.name == "__init__.py"
                    or not entry.stem.isidentifier()
                ):
                    continue

                module_parts = (
                    *package_parts,
                    entry.stem,
                )

                add_module(
                    entry,
                    ".".join(module_parts),
                    is_package=False,
                )

            elif entry.is_dir():
                if (
                    entry.name in IGNORED_DIRECTORIES
                    or entry.name.startswith(".")
                    or not entry.name.isidentifier()
                ):
                    continue

                init_file = entry / "__init__.py"

                if (
                    init_file.is_symlink()
                    or not init_file.is_file()
                ):
                    continue

                scan_directory(
                    entry,
                    (*package_parts, entry.name),
                )

    scan_directory(root, ())

    return sorted(
        modules,
        key=lambda module: module.module_name,
    )
