from pathlib import Path

from app.analysis.cross_file import (
    CrossFileCall,
    find_cross_file_calls,
)

DATABASE_SOURCE = (
    "def get_user():\n"
    "    return {'id': 1}\n"
)


def create_repository(
    tmp_path: Path,
    files: dict[str, str],
) -> Path:
    root = tmp_path / "repository"
    root.mkdir()

    for filename, content in files.items():
        (root / filename).write_text(
            content,
            encoding="utf-8",
        )

    return root


def test_resolves_cross_file_import(
    tmp_path: Path,
) -> None:
    root = create_repository(
        tmp_path,
        {
            "database.py": DATABASE_SOURCE,
            "auth.py": (
                "from database import get_user\n\n\n"
                "def login():\n"
                "    return get_user()\n"
            ),
        },
    )

    results = find_cross_file_calls(root)

    assert results == [
        CrossFileCall(
            caller="auth.py::login",
            target="database.py::get_user",
            line=5,
        )
    ]


def test_resolves_import_alias(
    tmp_path: Path,
) -> None:
    root = create_repository(
        tmp_path,
        {
            "database.py": DATABASE_SOURCE,
            "auth.py": (
                "from database import get_user as fetch_user\n\n"
                "def login():\n"
                "    return fetch_user()\n"
            ),
        },
    )

    results = find_cross_file_calls(root)

    assert len(results) == 1
    assert results[0].caller == "auth.py::login"
    assert results[0].target == "database.py::get_user"
    assert results[0].line == 4


def test_detects_multiple_call_sites(
    tmp_path: Path,
) -> None:
    root = create_repository(
        tmp_path,
        {
            "database.py": DATABASE_SOURCE,
            "auth.py": (
                "from database import get_user\n\n"
                "def login():\n"
                "    first = get_user()\n"
                "    return get_user()\n"
            ),
        },
    )

    results = find_cross_file_calls(root)

    assert len(results) == 2
    assert [result.line for result in results] == [4, 5]
    assert all(
        result.target == "database.py::get_user"
        for result in results
    )


def test_ignores_external_module(
    tmp_path: Path,
) -> None:
    root = create_repository(
        tmp_path,
        {
            "auth.py": (
                "from external_package import get_user\n\n"
                "def login():\n"
                "    return get_user()\n"
            ),
        },
    )

    assert find_cross_file_calls(root) == []


def test_ignores_missing_target_function(
    tmp_path: Path,
) -> None:
    root = create_repository(
        tmp_path,
        {
            "database.py": "def save_user():\n    pass\n",
            "auth.py": (
                "from database import get_user\n\n"
                "def login():\n"
                "    return get_user()\n"
            ),
        },
    )

    assert find_cross_file_calls(root) == []


def test_ignores_duplicate_target_definitions(
    tmp_path: Path,
) -> None:
    root = create_repository(
        tmp_path,
        {
            "database.py": (
                "def get_user():\n"
                "    return 1\n\n"
                "def get_user():\n"
                "    return 2\n"
            ),
            "auth.py": (
                "from database import get_user\n\n"
                "def login():\n"
                "    return get_user()\n"
            ),
        },
    )

    assert find_cross_file_calls(root) == []


def test_parameter_shadowing_blocks_match(
    tmp_path: Path,
) -> None:
    root = create_repository(
        tmp_path,
        {
            "database.py": DATABASE_SOURCE,
            "auth.py": (
                "from database import get_user\n\n"
                "def login(get_user):\n"
                "    return get_user()\n"
            ),
        },
    )

    assert find_cross_file_calls(root) == []


def test_module_rebinding_blocks_match(
    tmp_path: Path,
) -> None:
    root = create_repository(
        tmp_path,
        {
            "database.py": DATABASE_SOURCE,
            "auth.py": (
                "from database import get_user\n"
                "get_user = lambda: None\n\n"
                "def login():\n"
                "    return get_user()\n"
            ),
        },
    )

    assert find_cross_file_calls(root) == []


def test_symlinked_target_module_is_ignored(
    tmp_path: Path,
) -> None:
    root = create_repository(
        tmp_path,
        {
            "auth.py": (
                "from database import get_user\n\n"
                "def login():\n"
                "    return get_user()\n"
            ),
        },
    )

    outside = tmp_path / "outside.py"
    outside.write_text(
        DATABASE_SOURCE,
        encoding="utf-8",
    )

    (root / "database.py").symlink_to(outside)

    assert find_cross_file_calls(root) == []
