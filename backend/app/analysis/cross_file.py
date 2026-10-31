import ast
import tokenize
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from app.analysis.python_parser import (
    PythonFileAnalysis,
    analyze_python_file,
)

MAX_ROOT_FILES = 100


@dataclass(frozen=True)
class CrossFileCall:
    caller: str
    target: str
    line: int
    confidence: Literal["candidate"] = "candidate"
    reason: str = (
        "Explicit module-level from-import "
        "and unique function definition"
    )


class ModuleBindingCollector(ast.NodeVisitor):
    """
    Collect bindings from the module scope only.

    Do not count variables or definitions belonging
    to nested functions, classes, or comprehensions.
    """

    def __init__(self) -> None:
        self.counts: Counter[str] = Counter()

    def visit_FunctionDef(
        self,
        node: ast.FunctionDef,
    ) -> None:
        self.counts[node.name] += 1

    def visit_AsyncFunctionDef(
        self,
        node: ast.AsyncFunctionDef,
    ) -> None:
        self.counts[node.name] += 1

    def visit_ClassDef(
        self,
        node: ast.ClassDef,
    ) -> None:
        self.counts[node.name] += 1

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            name = (
                alias.asname
                or alias.name.split(".")[0]
            )
            self.counts[name] += 1

    def visit_ImportFrom(
        self,
        node: ast.ImportFrom,
    ) -> None:
        for alias in node.names:
            if alias.name != "*":
                name = alias.asname or alias.name
                self.counts[name] += 1

    def visit_Name(self, node: ast.Name) -> None:
        if isinstance(
            node.ctx,
            (ast.Store, ast.Del),
        ):
            self.counts[node.id] += 1

    def visit_ExceptHandler(
        self,
        node: ast.ExceptHandler,
    ) -> None:
        if node.name is not None:
            self.counts[node.name] += 1

        self.generic_visit(node)

    def visit_Lambda(self, node: ast.Lambda) -> None:
        pass

    def visit_ListComp(
        self,
        node: ast.ListComp,
    ) -> None:
        pass

    def visit_SetComp(
        self,
        node: ast.SetComp,
    ) -> None:
        pass

    def visit_DictComp(
        self,
        node: ast.DictComp,
    ) -> None:
        pass

    def visit_GeneratorExp(
        self,
        node: ast.GeneratorExp,
    ) -> None:
        pass


def _read_tree(path: Path) -> ast.Module:
    with tokenize.open(path) as stream:
        return ast.parse(
            stream.read(),
            filename=str(path),
        )


def _binding_counts(
    tree: ast.Module,
) -> Counter[str]:
    collector = ModuleBindingCollector()
    collector.visit(tree)
    return collector.counts


def _shadowed_in_function(
    analysis: PythonFileAnalysis,
    caller: str,
    name: str,
) -> bool:
    defined = {
        symbol.qualified_name
        for symbol in analysis.symbols
    }

    class_scopes = {
        symbol.qualified_name
        for symbol in analysis.symbols
        if symbol.kind == "class"
    }

    current = caller

    while current:
        # Python class bodies are not lexical scopes
        # for bare-name lookup inside methods.
        if current not in class_scopes:
            if name in analysis.other_bindings.get(
                current, []
            ):
                return True

            if f"{current}.{name}" in defined:
                return True

        current, _, _ = current.rpartition(".")

    return False


def find_cross_file_calls(
    repository_root: str | Path,
) -> list[CrossFileCall]:
    root = Path(repository_root).expanduser()

    if root.is_symlink() or not root.is_dir():
        raise ValueError(
            "Repository root must be a real directory"
        )

    modules = {
        path.stem: path
        for path in sorted(root.iterdir())
        if path.suffix == ".py"
        and path.stem.isidentifier()
        and path.is_file()
        and not path.is_symlink()
    }

    if len(modules) > MAX_ROOT_FILES:
        raise ValueError(
            "Repository exceeds supported module limit"
        )

    analyzed = {
        name: analyze_python_file(path)
        for name, path in modules.items()
    }

    results: list[CrossFileCall] = []

    for source_name, source_path in modules.items():
        source = analyzed[source_name]
        tree = _read_tree(source_path)

        # Only module-level bindings are counted.
        bindings = _binding_counts(tree)

        source_symbols = Counter(
            symbol.qualified_name
            for symbol in source.symbols
        )

        imports: dict[str, tuple[str, str]] = {}

        for node in tree.body:
            if not isinstance(node, ast.ImportFrom):
                continue

            if node.level != 0:
                continue

            if node.module not in modules:
                continue

            if node.module == source_name:
                continue

            for alias in node.names:
                local_name = (
                    alias.asname or alias.name
                )

                if bindings[local_name] == 1:
                    imports[local_name] = (
                        node.module,
                        alias.name,
                    )

        for call in source.calls:
            if (
                call.kind != "name"
                or call.caller is None
            ):
                continue

            if source_symbols[call.caller] != 1:
                continue

            if call.callee not in imports:
                continue

            if _shadowed_in_function(
                source,
                call.caller,
                call.callee,
            ):
                continue

            target_module, target_name = (
                imports[call.callee]
            )

            target = analyzed[target_module]

            matches = [
                symbol
                for symbol in target.symbols
                if symbol.kind == "function"
                and symbol.qualified_name == target_name
            ]

            if len(matches) != 1:
                continue

            results.append(
                CrossFileCall(
                    caller=(
                        f"{source_path.name}::"
                        f"{call.caller}"
                    ),
                    target=(
                        f"{modules[target_module].name}"
                        f"::{target_name}"
                    ),
                    line=call.line,
                )
            )

    return sorted(
        results,
        key=lambda item: (
            item.caller,
            item.line,
            item.target,
        ),
    )
