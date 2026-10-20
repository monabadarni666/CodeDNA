from pathlib import Path

from app.analysis.python_parser import analyze_python_file
from app.analysis.symbol_resolver import resolve_local_calls


def resolve_source(tmp_path: Path, source: str):
    file_path = tmp_path / "sample.py"
    file_path.write_text(source, encoding="utf-8")

    analysis = analyze_python_file(file_path)
    return resolve_local_calls(analysis)


def test_parameter_shadowing(tmp_path: Path) -> None:
    source = """
def helper():
    pass

def process(helper):
    return helper()
"""

    results = resolve_source(tmp_path, source)

    assert len(results) == 1
    assert results[0].status == "unresolved"
    assert results[0].target is None


def test_assignment_shadowing(tmp_path: Path) -> None:
    source = """
def helper():
    pass

def process():
    helper = lambda: 1
    return helper()
"""

    results = resolve_source(tmp_path, source)

    assert len(results) == 1
    assert results[0].status == "unresolved"


def test_outer_scope_parameter_shadowing(
    tmp_path: Path,
) -> None:
    source = """
def helper():
    pass

def outer(helper):
    def inner():
        return helper()

    return inner()
"""

    results = resolve_source(tmp_path, source)

    assert len(results) == 2
    assert results[0].callee == "helper"
    assert results[0].status == "unresolved"
    assert results[1].target == "outer.inner"
    assert results[1].status == "candidate"


def test_import_shadowing(tmp_path: Path) -> None:
    source = """
def helper():
    pass

def process():
    from somewhere import helper
    return helper()
"""

    results = resolve_source(tmp_path, source)

    assert len(results) == 1
    assert results[0].status == "unresolved"


def test_module_assignment_shadowing(
    tmp_path: Path,
) -> None:
    source = """
def helper():
    pass

helper = None
helper()
"""

    results = resolve_source(tmp_path, source)

    assert len(results) == 1
    assert results[0].status == "unresolved"
