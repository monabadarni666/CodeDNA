from collections import Counter
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Literal

from app.analysis.python_parser import PythonFileAnalysis

ResolutionStatus = Literal[
    "candidate",
    "ambiguous",
    "unresolved",
]


@dataclass(frozen=True)
class CallResolution:
    caller: str | None
    callee: str
    line: int
    target: str | None
    status: ResolutionStatus
    reason: str


def _lexical_candidates(
    caller: str | None,
    callee: str,
    symbol_kinds: dict[str, str],
) -> Iterator[tuple[str, str]]:
    scope = caller

    while scope:
        if symbol_kinds.get(scope) in {
            "function",
            "method",
        }:
            yield f"{scope}.{callee}", scope

        scope, _, _ = scope.rpartition(".")

    yield callee, "<module>"


def resolve_local_calls(
    analysis: PythonFileAnalysis,
) -> list[CallResolution]:
    symbol_counts = Counter(
        symbol.qualified_name
        for symbol in analysis.symbols
        if symbol.kind in {"function", "method"}
    )

    symbol_kinds = {
        symbol.qualified_name: symbol.kind
        for symbol in analysis.symbols
    }

    resolutions: list[CallResolution] = []

    for call in analysis.calls:
        if call.kind != "name":
            resolutions.append(
                CallResolution(
                    caller=call.caller,
                    callee=call.callee,
                    line=call.line,
                    target=None,
                    status="unresolved",
                    reason=(
                        "Attribute or dynamic call requires "
                        "deeper analysis"
                    ),
                )
            )
            continue

        matched = False

        for candidate, scope in _lexical_candidates(
            call.caller,
            call.callee,
            symbol_kinds,
        ):
            if call.callee in analysis.other_bindings.get(
                scope, []
            ):
                matched = True

                resolutions.append(
                    CallResolution(
                        caller=call.caller,
                        callee=call.callee,
                        line=call.line,
                        target=None,
                        status="unresolved",
                        reason=(
                            "Name is also bound by parameter, "
                            "assignment, class, or import "
                            f"in scope {scope}; "
                            "resolution is unsafe"
                        ),
                    )
                )
                break

            count = symbol_counts[candidate]

            if count == 0:
                continue

            matched = True

            if count == 1:
                resolutions.append(
                    CallResolution(
                        caller=call.caller,
                        callee=call.callee,
                        line=call.line,
                        target=candidate,
                        status="candidate",
                        reason=(
                            "Unique matching lexical definition; "
                            "runtime binding is not guaranteed"
                        ),
                    )
                )
            else:
                resolutions.append(
                    CallResolution(
                        caller=call.caller,
                        callee=call.callee,
                        line=call.line,
                        target=None,
                        status="ambiguous",
                        reason=(
                            "Multiple definitions match "
                            "the same qualified name"
                        ),
                    )
                )

            break

        if not matched:
            resolutions.append(
                CallResolution(
                    caller=call.caller,
                    callee=call.callee,
                    line=call.line,
                    target=None,
                    status="unresolved",
                    reason="No matching local definition found",
                )
            )

    return resolutions
