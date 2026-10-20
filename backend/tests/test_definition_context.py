from pathlib import Path

from app.analysis.python_parser import analyze_python_file


def test_function_decorators_and_defaults(
    tmp_path: Path,
) -> None:
    source = """
def register():
    return lambda func: func

def factory():
    return 42

@register()
def process(value=factory()):
    return factory()
"""

    file_path = tmp_path / "example.py"
    file_path.write_text(source, encoding="utf-8")

    result = analyze_python_file(file_path)

    calls = [
        (call.callee, call.caller)
        for call in result.calls
    ]

    assert calls == [
        ("register", None),
        ("factory", None),
        ("factory", "process"),
    ]


def test_nested_function_definition_context(
    tmp_path: Path,
) -> None:
    source = """
def outer():
    def factory():
        return 1

    @register()
    def inner(value=factory()):
        return factory()

    return inner()
"""

    file_path = tmp_path / "nested.py"
    file_path.write_text(source, encoding="utf-8")

    result = analyze_python_file(file_path)

    calls = [
        (call.callee, call.caller)
        for call in result.calls
    ]

    assert calls == [
        ("register", "outer"),
        ("factory", "outer"),
        ("factory", "outer.inner"),
        ("inner", "outer"),
    ]


def test_class_body_execution_context(
    tmp_path: Path,
) -> None:
    source = """
def factory():
    return 1

class Service:
    @trace()
    def run(self, value=factory()):
        return factory()

    ready = factory()
"""

    file_path = tmp_path / "service.py"
    file_path.write_text(source, encoding="utf-8")

    result = analyze_python_file(file_path)

    calls = [
        (call.callee, call.caller)
        for call in result.calls
    ]

    assert calls == [
        ("trace", None),
        ("factory", None),
        ("factory", "Service.run"),
        ("factory", None),
    ]
