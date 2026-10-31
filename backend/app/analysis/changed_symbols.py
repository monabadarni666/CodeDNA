import ast
from collections import defaultdict
from dataclasses import dataclass
from typing import Literal

ChangeType = Literal["added", "deleted", "modified"]
SymbolKind = Literal["function", "method"]


@dataclass(frozen=True)
class ChangedSymbol:
    qualified_name: str
    kind: SymbolKind
    change_type: ChangeType
    old_line: int | None
    new_line: int | None


@dataclass(frozen=True)
class _Definition:
    kind: SymbolKind
    line: int
    fingerprint: str


class _SymbolCollector(ast.NodeVisitor):
    def __init__(self) -> None:
        self.scopes: list[tuple[str, str]] = []
        self.definitions: dict[
            str, list[_Definition]
        ] = defaultdict(list)

    def visit_ClassDef(
        self,
        node: ast.ClassDef,
    ) -> None:
        self.scopes.append((node.name, "class"))

        for statement in node.body:
            self.visit(statement)

        self.scopes.pop()

    def _visit_function(
        self,
        node: ast.FunctionDef | ast.AsyncFunctionDef,
    ) -> None:
        kind: SymbolKind = (
            "method"
            if self.scopes
            and self.scopes[-1][1] == "class"
            else "function"
        )

        qualified_name = ".".join(
            [
                *(name for name, _ in self.scopes),
                node.name,
            ]
        )

        fingerprint = ast.dump(
            node,
            include_attributes=False,
        )

        self.definitions[qualified_name].append(
            _Definition(
                kind=kind,
                line=node.lineno,
                fingerprint=fingerprint,
            )
        )

        self.scopes.append((node.name, "function"))

        for statement in node.body:
            self.visit(statement)

        self.scopes.pop()

    def visit_FunctionDef(
        self,
        node: ast.FunctionDef,
    ) -> None:
        self._visit_function(node)

    def visit_AsyncFunctionDef(
        self,
        node: ast.AsyncFunctionDef,
    ) -> None:
        self._visit_function(node)


def _collect_symbols(
    source: str,
) -> dict[str, list[_Definition]]:
    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        raise ValueError(
            "Invalid Python syntax in compared source"
        ) from exc

    collector = _SymbolCollector()
    collector.visit(tree)

    return collector.definitions


def compare_python_sources(
    old_source: str | None,
    new_source: str | None,
) -> list[ChangedSymbol]:
    """
    Compare Python functions and methods by AST.

    This does not execute the source code.

    A changed nested function can also mark its
    enclosing function as modified.

    Ambiguous duplicate definitions are skipped.
    """
    if old_source is None and new_source is None:
        raise ValueError(
            "At least one source version is required"
        )

    old = _collect_symbols(old_source or "")
    new = _collect_symbols(new_source or "")

    results: list[ChangedSymbol] = []

    for name in sorted(set(old) | set(new)):
        old_matches = old.get(name, [])
        new_matches = new.get(name, [])

        # Do not guess which duplicate definition
        # corresponds to a changed symbol.
        if (
            len(old_matches) > 1
            or len(new_matches) > 1
        ):
            continue

        before = old_matches[0] if old_matches else None
        after = new_matches[0] if new_matches else None

        if before is None and after is not None:
            change_type: ChangeType = "added"

        elif after is None and before is not None:
            change_type = "deleted"

        elif before is not None and after is not None:
            if (
                before.fingerprint == after.fingerprint
                and before.kind == after.kind
            ):
                continue

            change_type = "modified"

        else:
            continue

        results.append(
            ChangedSymbol(
                qualified_name=name,
                kind=(
                    after.kind
                    if after is not None
                    else before.kind
                ),
                change_type=change_type,
                old_line=(
                    before.line
                    if before is not None
                    else None
                ),
                new_line=(
                    after.line
                    if after is not None
                    else None
                ),
            )
        )

    return results
