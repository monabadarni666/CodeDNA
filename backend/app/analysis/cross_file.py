import ast
import tokenize
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from app.analysis.module_discovery import (
    MAX_SUPPORTED_MODULES,
    PythonModule,
    discover_python_modules,
)
from app.analysis.python_parser import (
    PythonFileAnalysis,
    analyze_python_file,
)

# Kept for compatibility with repository_graph.py.
MAX_ROOT_FILES = MAX_SUPPORTED_MODULES


@dataclass(frozen=True)
class CrossFileCall:
    caller: str
    target: str
    line: int
    confidence: Literal["candidate"] = "candidate"
    reason: str = (
        "Explicit from-import and unique "
        "function definition"
    )


class ModuleBindingCollector(ast.NodeVisitor):
    """Collect bindings at module scope only."""

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

    def visit_Import(
        self,
        node: ast.Import,
    ) -> None:
        for alias in node.names:
            name = alias.asname or alias.name.split(".")[0]
            self.counts[name] += 1

    def visit_ImportFrom(
        self,
        node: ast.ImportFrom,
    ) -> None:
        for alias in node.names:
            if alias.name != "*":
                self.counts[
                    alias.asname or alias.name
                ] += 1

    def visit_Name(
        self,
        node: ast.Name,
    ) -> None:
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

    def visit_Lambda(
        self,
        node: ast.Lambda,
    ) -> None:
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
        if current not in class_scopes:
            if name in analysis.other_bindings.get(
                current, []
            ):
                return True

            if f"{current}.{name}" in defined:
                return True

        current, _, _ = current.rpartition(".")

    return False


def _resolve_import_module_name(
    source: PythonModule,
    node: ast.ImportFrom,
) -> str | None:
    """
    Resolve an absolute or relative from-import
    to a discovered module name.

    Examples:
      from app.users import get_user -> app.users
      from .users import get_user    -> app.users
      from ..database import get_user -> app.database
    """
    if node.level == 0:
        return node.module

    parts = source.module_name.split(".")

    if not source.is_package:
        parts = parts[:-1]

    if node.level > len(parts):
        return None

    prefix_length = len(parts) - node.level + 1
    resolved_parts = parts[:prefix_length]

    if node.module:
        resolved_parts.extend(node.module.split("."))

    if not resolved_parts:
        return None

    return ".".join(resolved_parts)


def find_cross_file_calls(
    repository_root: str | Path,
) -> list[CrossFileCall]:
    root = Path(repository_root).expanduser()

    # Discover both root modules and regular packages.
    modules = discover_python_modules(root)

    module_map = {
        module.module_name: module
        for module in modules
    }

    # Reuse the existing AST analysis engine.
    analyzed = {
        module.module_name: analyze_python_file(
            module.path
        )
        for module in modules
    }

    results: list[CrossFileCall] = []

    for source_module in modules:
        source_name = source_module.module_name
        source = analyzed[source_name]
        tree = _read_tree(source_module.path)

        bindings = _binding_counts(tree)

        source_symbols = Counter(
            symbol.qualified_name
            for symbol in source.symbols
        )

        imports: dict[str, tuple[str, str]] = {}

        # Only explicit module-level from-imports.
        for node in tree.body:
            if not isinstance(node, ast.ImportFrom):
                continue

            target_module_name = (
                _resolve_import_module_name(
                    source_module,
                    node,
                )
            )

            if target_module_name not in module_map:
                continue

            if target_module_name == source_name:
                continue

            for alias in node.names:
                if alias.name == "*":
                    continue

                local_name = (
                    alias.asname or alias.name
                )

                # Reject ambiguous module bindings.
                if bindings[local_name] != 1:
                    continue

                imports[local_name] = (
                    target_module_name,
                    alias.name,
                )

        for call in source.calls:
            if (
                call.kind != "name"
                or call.caller is None
            ):
                continue

            # Only unique caller definitions.
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

            target_module_name, target_name = (
                imports[call.callee]
            )

            target = analyzed[target_module_name]

            matches = [
                symbol
                for symbol in target.symbols
                if symbol.kind == "function"
                and symbol.qualified_name == target_name
            ]

            # Do not guess ambiguous or missing targets.
            if len(matches) != 1:
                continue

            target_module = module_map[
                target_module_name
            ]

            results.append(
                CrossFileCall(
                    caller=(
                        f"{source_module.relative_path}"
                        f"::{call.caller}"
                    ),
                    target=(
                        f"{target_module.relative_path}"
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
