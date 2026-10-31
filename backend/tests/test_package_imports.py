from pathlib import Path

from app.analysis.cross_file import find_cross_file_calls

USER_SOURCE = (
    "def get_user():\n"
    "    return {'id': 1}\n"
)


def create_repository(
    tmp_path: Path,
    files: dict[str, str],
) -> Path:
    root = tmp_path / "repository"
    root.mkdir()

    for filename, source in files.items():
        path = root / filename
        path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )
        path.write_text(
            source,
            encoding="utf-8",
        )

    return root


def get_dependencies(root: Path) -> set[tuple[str, str]]:
    return {
        (call.caller, call.target)
        for call in find_cross_file_calls(root)
    }


def test_absolute_import_from_nested_package(
    tmp_path: Path,
) -> None:
    root = create_repository(
        tmp_path,
        {
            "app/__init__.py": "",
            "app/services/__init__.py": "",
            "app/services/users.py": USER_SOURCE,
            "app/auth.py": (
                "from app.services.users import get_user\n\n\n"
                "def login():\n"
                "    return get_user()\n"
            ),
        },
    )

    assert get_dependencies(root) == {
        (
            "app/auth.py::login",
            "app/services/users.py::get_user",
        ),
    }


def test_relative_import_from_sibling_module(
    tmp_path: Path,
) -> None:
    root = create_repository(
        tmp_path,
        {
            "app/__init__.py": "",
            "app/users.py": USER_SOURCE,
            "app/auth.py": (
                "from .users import get_user\n\n\n"
                "def login():\n"
                "    return get_user()\n"
            ),
        },
    )

    assert get_dependencies(root) == {
        (
            "app/auth.py::login",
            "app/users.py::get_user",
        ),
    }


def test_relative_import_from_parent_package(
    tmp_path: Path,
) -> None:
    root = create_repository(
        tmp_path,
        {
            "app/__init__.py": "",
            "app/database.py": USER_SOURCE,
            "app/services/__init__.py": "",
            "app/services/auth.py": (
                "from ..database import get_user\n\n\n"
                "def login():\n"
                "    return get_user()\n"
            ),
        },
    )

    assert get_dependencies(root) == {
        (
            "app/services/auth.py::login",
            "app/database.py::get_user",
        ),
    }


def test_absolute_import_with_alias(
    tmp_path: Path,
) -> None:
    root = create_repository(
        tmp_path,
        {
            "app/__init__.py": "",
            "app/services/__init__.py": "",
            "app/services/users.py": USER_SOURCE,
            "app/auth.py": (
                "from app.services.users "
                "import get_user as fetch_user\n\n\n"
                "def login():\n"
                "    return fetch_user()\n"
            ),
        },
    )

    assert get_dependencies(root) == {
        (
            "app/auth.py::login",
            "app/services/users.py::get_user",
        ),
    }


def test_import_function_from_package_init(
    tmp_path: Path,
) -> None:
    root = create_repository(
        tmp_path,
        {
            "app/__init__.py": "",
            "app/services/__init__.py": USER_SOURCE,
            "app/auth.py": (
                "from app.services import get_user\n\n\n"
                "def login():\n"
                "    return get_user()\n"
            ),
        },
    )

    assert get_dependencies(root) == {
        (
            "app/auth.py::login",
            "app/services/__init__.py::get_user",
        ),
    }


def test_dependency_chain_across_packages(
    tmp_path: Path,
) -> None:
    root = create_repository(
        tmp_path,
        {
            "app/__init__.py": "",
            "app/services/__init__.py": "",
            "app/services/users.py": USER_SOURCE,
            "app/auth.py": (
                "from app.services.users import get_user\n\n\n"
                "def login():\n"
                "    return get_user()\n"
            ),
            "main.py": (
                "from app.auth import login\n\n\n"
                "def start():\n"
                "    return login()\n"
            ),
        },
    )

    assert get_dependencies(root) == {
        (
            "main.py::start",
            "app/auth.py::login",
        ),
        (
            "app/auth.py::login",
            "app/services/users.py::get_user",
        ),
    }


def test_root_level_import_still_works(
    tmp_path: Path,
) -> None:
    root = create_repository(
        tmp_path,
        {
            "database.py": USER_SOURCE,
            "auth.py": (
                "from database import get_user\n\n\n"
                "def login():\n"
                "    return get_user()\n"
            ),
        },
    )

    assert get_dependencies(root) == {
        (
            "auth.py::login",
            "database.py::get_user",
        ),
    }
