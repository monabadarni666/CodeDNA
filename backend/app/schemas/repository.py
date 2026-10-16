from pydantic import BaseModel, Field


class RepositoryScanRequest(BaseModel):
    repository: str = Field(
        min_length=1,
        max_length=64,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]*$",
        description="Repository folder name inside workspaces",
    )


class RepositoryScanResponse(BaseModel):
    repository: str
    total_source_files: int
    languages: dict[str, int]
    files: list[str]
