from pathlib import Path

import pytest

from app.analysis.python_parser import (
    MAX_FILE_SIZE,
    analyze_python_file,
)


@pytest.fixture
def example_python_file(tmp_path: Path) -> Path:
    file_path = tmp_path / "user_service.py"

    file_path.write_text(
        """import os
from pathlib import Path

class UserService:
    def validate_user(self, user_id: int) -> bool:
        def normalize(value: int) -> int:
            return abs(value)
        return normalize(user_id) > 0

    async def fetch_user(self) -> str:
        return os.getenv("DEMO_USER", "guest")

def get_home() -> Path:
    return Path.home()
""",
        encoding="utf-8",
    )

    return file_path


def test_extracts_symbols_and_imports(
    example_python_file: Path,
) -> None:
    result = analyze_python_file(example_python_file)

    symbols = [
        (symbol.qualified_name, symbol.kind)
        for symbol in result.symbols
    ]

    assert symbols == [
        ("UserService", "class"),
        ("UserService.validate_user", "method"),
        (
            "UserService.validate_user.normalize",
            "function",
        ),
        ("UserService.fetch_user", "method"),
        ("get_home", "function"),
    ]

    imports = [
        (item.module, item.names)
        for item in result.imports
    ]

    assert imports == [
        ("os", []),
        ("pathlib", ["Path"]),
    ]


def test_detects_function_calls(
    example_python_file: Path,
) -> None:
    result = analyze_python_file(example_python_file)

    calls = [
        (call.caller, call.callee, call.kind)
        for call in result.calls
    ]

    assert calls == [
        (
            "UserService.validate_user.normalize",
            "abs",
            "name",
        ),
        (
            "UserService.validate_user",
            "normalize",
            "name",
        ),
        (
            "UserService.fetch_user",
            "os.getenv",
            "attribute",
        ),
        (
            "get_home",
            "Path.home",
            "attribute",
        ),
    ]


def test_module_level_and_dynamic_calls(
    tmp_path: Path,
) -> None:
    file_path = tmp_path / "dynamic.py"

    file_path.write_text(
        'print("ready")\nfactory()("value")\n',
        encoding="utf-8",
    )

    result = analyze_python_file(file_path)

    calls = [
        (call.caller, call.callee, call.kind)
        for call in result.calls
    ]

    assert calls == [
        (None, "print", "name"),
        (None, "factory()", "dynamic"),
        (None, "factory", "name"),
    ]


def test_invalid_python_syntax(
    tmp_path: Path,
) -> None:
    file_path = tmp_path / "broken.py"

    file_path.write_text(
        "def broken(:\n    pass\n",
        encoding="utf-8",
    )

    with pytest.raises(
        ValueError,
        match="Invalid Python syntax",
    ):
        analyze_python_file(file_path)


def test_rejects_invalid_file_paths(
    tmp_path: Path,
) -> None:
    missing = tmp_path / "missing.py"

    with pytest.raises(
        ValueError,
        match="Python file not found",
    ):
        analyze_python_file(missing)

    text_file = tmp_path / "notes.txt"
    text_file.write_text("hello", encoding="utf-8")

    with pytest.raises(
        ValueError,
        match="Only Python files are supported",
    ):
        analyze_python_file(text_file)


def test_rejects_oversized_files(
    tmp_path: Path,
) -> None:
    file_path = tmp_path / "large.py"

    file_path.write_bytes(
        b"x" * (MAX_FILE_SIZE + 1)
    )

    with pytest.raises(
        ValueError,
        match="Python file exceeds size limit",
    ):
        analyze_python_file(file_path)


def test_rejects_symbolic_links(
    tmp_path: Path,
) -> None:
    original = tmp_path / "original.py"
    original.write_text("x = 1\n", encoding="utf-8")

    link = tmp_path / "linked.py"
    link.symlink_to(original)

    with pytest.raises(
        ValueError,
        match="Symbolic links are not supported",
    ):
        analyze_python_file(link)
