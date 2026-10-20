from typing import Literal

from pydantic import BaseModel, Field, field_validator

from app.schemas.repository import RepositoryScanRequest


class PythonAnalysisRequest(RepositoryScanRequest):
    file: str = Field(
        min_length=4,
        max_length=512,
        description="Relative Python file path inside repository",
    )

    @field_validator("file")
    @classmethod
    def validate_file(cls, value: str) -> str:
        parts = value.split("/")

        if (
            "\\" in value
            or "\x00" in value
            or any(part in {"", ".", ".."} for part in parts)
            or not value.lower().endswith(".py")
        ):
            raise ValueError(
                "File must be a relative .py path "
                "without directory traversal"
            )

        return value


class SymbolResult(BaseModel):
    name: str
    qualified_name: str
    kind: Literal["class", "function", "method"]
    line: int
    end_line: int | None


class ImportResult(BaseModel):
    module: str
    names: list[str]
    line: int


class CallResult(BaseModel):
    caller: str | None
    callee: str
    kind: Literal["name", "attribute", "dynamic"]
    line: int


class ResolutionResult(BaseModel):
    caller: str | None
    callee: str
    line: int
    target: str | None
    status: Literal["candidate", "ambiguous", "unresolved"]
    reason: str


class PythonAnalysisResponse(BaseModel):
    repository: str
    file: str
    symbols: list[SymbolResult]
    imports: list[ImportResult]
    calls: list[CallResult]
    resolutions: list[ResolutionResult]
    other_bindings: dict[str, list[str]]
