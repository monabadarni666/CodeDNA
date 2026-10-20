import ast
import tokenize
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

MAX_FILE_SIZE = 1_000_000

SymbolKind = Literal["class", "function", "method"]
CallKind = Literal["name", "attribute", "dynamic"]


@dataclass(frozen=True)
class CodeSymbol:
    name: str
    qualified_name: str
    kind: SymbolKind
    line: int
    end_line: int | None


@dataclass(frozen=True)
class ImportInfo:
    module: str
    names: list[str]
    line: int


@dataclass(frozen=True)
class CodeCall:
    caller: str | None
    callee: str
    kind: CallKind
    line: int


@dataclass
class PythonFileAnalysis:
    file: str
    symbols: list[CodeSymbol]
    imports: list[ImportInfo]
    calls: list[CodeCall]
    other_bindings: dict[str, list[str]] = field(
        default_factory=dict
    )


class PythonASTVisitor(ast.NodeVisitor):
    def __init__(self) -> None:
        self.symbols: list[CodeSymbol] = []
        self.imports: list[ImportInfo] = []
        self.calls: list[CodeCall] = []
        self.scope: list[tuple[str, str]] = []
        self.other_bindings: dict[str, set[str]] = {}

    def _binding_scope(self) -> str | None:
        if not self.scope:
            return "<module>"

        if self.scope[-1][1] == "function":
            return ".".join(
                name for name, _ in self.scope
            )

        return None

    def _register_other_binding(self, name: str) -> None:
        scope = self._binding_scope()

        if scope is not None:
            self.other_bindings.setdefault(
                scope, set()
            ).add(name)

    def _add_symbol(
        self,
        node: ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef,
        kind: SymbolKind,
    ) -> None:
        names = [name for name, _ in self.scope]
        qualified_name = ".".join([*names, node.name])

        self.symbols.append(
            CodeSymbol(
                name=node.name,
                qualified_name=qualified_name,
                kind=kind,
                line=node.lineno,
                end_line=node.end_lineno,
            )
        )

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        self._register_other_binding(node.name)
        self._add_symbol(node, "class")

        self.scope.append((node.name, "class"))
        self.generic_visit(node)
        self.scope.pop()

    def _visit_function(
        self,
        node: ast.FunctionDef | ast.AsyncFunctionDef,
    ) -> None:
        is_method = bool(
            self.scope and self.scope[-1][1] == "class"
        )

        kind: SymbolKind = (
            "method" if is_method else "function"
        )

        self._add_symbol(node, kind)
        self.scope.append((node.name, "function"))

        arguments = node.args

        for arg in [
            *arguments.posonlyargs,
            *arguments.args,
            *arguments.kwonlyargs,
        ]:
            self._register_other_binding(arg.arg)

        if arguments.vararg is not None:
            self._register_other_binding(
                arguments.vararg.arg
            )

        if arguments.kwarg is not None:
            self._register_other_binding(
                arguments.kwarg.arg
            )

        self.generic_visit(node)
        self.scope.pop()

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._visit_function(node)

    def visit_AsyncFunctionDef(
        self,
        node: ast.AsyncFunctionDef,
    ) -> None:
        self._visit_function(node)

    def visit_Name(self, node: ast.Name) -> None:
        if isinstance(node.ctx, (ast.Store, ast.Del)):
            self._register_other_binding(node.id)

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            bound_name = (
                alias.asname or alias.name.split(".")[0]
            )
            self._register_other_binding(bound_name)

            self.imports.append(
                ImportInfo(
                    module=alias.name,
                    names=[],
                    line=node.lineno,
                )
            )

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        module = "." * node.level + (node.module or "")

        for alias in node.names:
            if alias.name != "*":
                self._register_other_binding(
                    alias.asname or alias.name
                )

        self.imports.append(
            ImportInfo(
                module=module,
                names=[alias.name for alias in node.names],
                line=node.lineno,
            )
        )

    def visit_Call(self, node: ast.Call) -> None:
        if isinstance(node.func, ast.Name):
            kind: CallKind = "name"
        elif isinstance(node.func, ast.Attribute):
            kind = "attribute"
        else:
            kind = "dynamic"

        caller = ".".join(
            name for name, _ in self.scope
        ) or None

        self.calls.append(
            CodeCall(
                caller=caller,
                callee=ast.unparse(node.func),
                kind=kind,
                line=node.lineno,
            )
        )

        self.generic_visit(node)


def analyze_python_file(
    path: str | Path,
) -> PythonFileAnalysis:
    file_path = Path(path).expanduser()

    if file_path.is_symlink():
        raise ValueError("Symbolic links are not supported")

    if not file_path.is_file():
        raise ValueError("Python file not found")

    if file_path.suffix.lower() != ".py":
        raise ValueError("Only Python files are supported")

    if file_path.stat().st_size > MAX_FILE_SIZE:
        raise ValueError("Python file exceeds size limit")

    try:
        with tokenize.open(file_path) as stream:
            source = stream.read()
    except (OSError, SyntaxError, UnicodeError) as exc:
        raise ValueError(
            "Unable to read Python file"
        ) from exc

    try:
        tree = ast.parse(
            source,
            filename=str(file_path),
        )
    except SyntaxError as exc:
        raise ValueError(
            f"Invalid Python syntax at line "
            f"{exc.lineno}: {exc.msg}"
        ) from exc

    visitor = PythonASTVisitor()
    visitor.visit(tree)

    return PythonFileAnalysis(
        file=file_path.as_posix(),
        symbols=visitor.symbols,
        imports=visitor.imports,
        calls=visitor.calls,
        other_bindings={
            scope: sorted(names)
            for scope, names in visitor.other_bindings.items()
        },
    )
