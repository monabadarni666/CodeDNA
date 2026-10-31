from pathlib import Path

from app.analysis.cross_file import find_cross_file_calls

DATABASE_SOURCE = (
    "def get_user():\n"
    "    return {'id': 1}\n"
)


def create_repository(
    tmp_path: Path,
    auth_source: str,
) -> Path:
    root = tmp_path / "repository"
    root.mkdir()

    (root / "database.py").write_text(
        DATABASE_SOURCE,
        encoding="utf-8",
    )

    (root / "auth.py").write_text(
        auth_source,
        encoding="utf-8",
    )

    return root


def assert_only_login_is_resolved(root: Path) -> None:
    results = find_cross_file_calls(root)

    assert len(results) == 1
    assert results[0].caller == "auth.py::login"
    assert results[0].target == "database.py::get_user"
    assert results[0].confidence == "candidate"


def test_unrelated_local_assignment(
    tmp_path: Path,
) -> None:
    source = """
from database import get_user

def unrelated():
    get_user = lambda: None
    return get_user()

def login():
    return get_user()
"""

    root = create_repository(tmp_path, source)

    assert_only_login_is_resolved(root)


def test_class_method_does_not_shadow_import(
    tmp_path: Path,
) -> None:
    source = """
from database import get_user

class LocalService:
    def get_user(self):
        return None

def login():
    return get_user()
"""

    root = create_repository(tmp_path, source)

    assert_only_login_is_resolved(root)


def test_nested_function_does_not_shadow_import(
    tmp_path: Path,
) -> None:
    source = """
from database import get_user

def unrelated():
    def get_user():
        return None

    return get_user()

def login():
    return get_user()
"""

    root = create_repository(tmp_path, source)

    assert_only_login_is_resolved(root)
