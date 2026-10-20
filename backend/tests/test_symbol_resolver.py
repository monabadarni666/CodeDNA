from pathlib import Path

from app.analysis.python_parser import analyze_python_file
from app.analysis.symbol_resolver import (
    CallResolution,
    resolve_local_calls,
)


def resolve_source(
    tmp_path: Path,
    source: str,
) -> list[CallResolution]:
    file_path = tmp_path / "example.py"
    file_path.write_text(source, encoding="utf-8")

    analysis = analyze_python_file(file_path)
    return resolve_local_calls(analysis)


def test_resolves_global_function(
    tmp_path: Path,
) -> None:
    source = """
def helper(value):
    return value

def process(value):
    return helper(value)
"""

    results = resolve_source(tmp_path, source)

    assert len(results) == 1
    assert results[0].caller == "process"
    assert results[0].callee == "helper"
    assert results[0].target == "helper"
    assert results[0].status == "candidate"


def test_prefers_nearest_nested_function(
    tmp_path: Path,
) -> None:
    source = """
def helper(value):
    return value

def process(value):
    def helper(value):
        return value + 1

    return helper(value)
"""

    results = resolve_source(tmp_path, source)

    assert len(results) == 1
    assert results[0].caller == "process"
    assert results[0].target == "process.helper"
    assert results[0].status == "candidate"


def test_duplicate_definitions_are_ambiguous(
    tmp_path: Path,
) -> None:
    source = """
def helper():
    pass

def helper():
    pass

helper()
"""

    results = resolve_source(tmp_path, source)

    assert len(results) == 1
    assert results[0].callee == "helper"
    assert results[0].status == "ambiguous"
    assert results[0].target is None


def test_external_calls_remain_unresolved(
    tmp_path: Path,
) -> None:
    source = """
import os

def action():
    print("hello")
    return os.getenv("NAME")
"""

    results = resolve_source(tmp_path, source)

    assert len(results) == 2

    assert results[0].callee == "print"
    assert results[0].status == "unresolved"

    assert results[1].callee == "os.getenv"
    assert results[1].status == "unresolved"


def test_dynamic_call_resolution(
    tmp_path: Path,
) -> None:
    source = """
def factory():
    return print

factory()("hello")
"""

    results = resolve_source(tmp_path, source)

    assert len(results) == 2

    dynamic_call = results[0]
    factory_call = results[1]

    assert dynamic_call.callee == "factory()"
    assert dynamic_call.status == "unresolved"

    assert factory_call.callee == "factory"
    assert factory_call.target == "factory"
    assert factory_call.status == "candidate"


def test_class_method_not_global_function(
    tmp_path: Path,
) -> None:
    source = """
class Handler:
    def handle(self):
        return True

handle()
"""

    results = resolve_source(tmp_path, source)

    assert len(results) == 1
    assert results[0].callee == "handle"
    assert results[0].status == "unresolved"
    assert results[0].target is None
