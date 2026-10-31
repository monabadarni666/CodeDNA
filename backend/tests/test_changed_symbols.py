import pytest

from app.analysis.changed_symbols import (
    compare_python_sources,
)


def test_modified_function() -> None:
    old = "def get_user():\n    return 1\n"
    new = "def get_user():\n    return 2\n"

    changes = compare_python_sources(old, new)

    assert len(changes) == 1

    change = changes[0]

    assert change.qualified_name == "get_user"
    assert change.change_type == "modified"
    assert change.kind == "function"
    assert change.old_line == 1
    assert change.new_line == 1


def test_added_function() -> None:
    changes = compare_python_sources(
        "",
        "def login():\n    return True\n",
    )

    assert len(changes) == 1
    assert changes[0].qualified_name == "login"
    assert changes[0].change_type == "added"
    assert changes[0].old_line is None


def test_deleted_function() -> None:
    changes = compare_python_sources(
        "def login():\n    return True\n",
        "",
    )

    assert len(changes) == 1
    assert changes[0].change_type == "deleted"
    assert changes[0].new_line is None


def test_formatting_and_comments_are_ignored() -> None:
    old = (
        "def calculate(x):\n"
        "    return x + 1\n"
    )

    new = (
        "# A new comment\n"
        "def calculate( x ):\n"
        "    # Another comment\n"
        "    return x + 1\n"
    )

    assert compare_python_sources(old, new) == []


def test_modified_class_method() -> None:
    old = (
        "class UserService:\n"
        "    def fetch(self):\n"
        "        return 1\n"
    )

    new = (
        "class UserService:\n"
        "    def fetch(self):\n"
        "        return 2\n"
    )

    changes = compare_python_sources(old, new)

    assert len(changes) == 1
    assert (
        changes[0].qualified_name
        == "UserService.fetch"
    )
    assert changes[0].kind == "method"
    assert changes[0].change_type == "modified"


def test_nested_function_change() -> None:
    old = (
        "def outer():\n"
        "    def inner():\n"
        "        return 1\n"
        "    return inner()\n"
    )

    new = (
        "def outer():\n"
        "    def inner():\n"
        "        return 2\n"
        "    return inner()\n"
    )

    changes = compare_python_sources(old, new)

    names = {
        change.qualified_name
        for change in changes
    }

    assert names == {
        "outer",
        "outer.inner",
    }


def test_invalid_syntax_is_rejected() -> None:
    with pytest.raises(
        ValueError,
        match="Invalid Python syntax",
    ):
        compare_python_sources(
            "def broken(:\n",
            "",
        )


def test_ambiguous_duplicate_definitions_are_skipped() -> None:
    old = (
        "def helper():\n"
        "    return 1\n\n"
        "def helper():\n"
        "    return 2\n"
    )

    new = (
        "def helper():\n"
        "    return 3\n"
    )

    assert compare_python_sources(old, new) == []
