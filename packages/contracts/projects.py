"""Minimal, authority-owned project metadata mutations."""
from pydantic import BaseModel, ConfigDict, Field, field_validator


class ProjectInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    name: str = Field(min_length=2, max_length=120)
    description: str = Field(default="", max_length=2000)
    idempotency_key: str = Field(pattern=r"^[a-zA-Z0-9_-]{16,100}$")

    @field_validator("name", "description")
    @classmethod
    def reject_controls(cls, value):
        if any(ord(char) < 32 and char not in "\n\t" for char in value):
            raise ValueError("Control characters are not supported.")
        return value

    @field_validator("name")
    @classmethod
    def single_line(cls, value):
        if "\n" in value or "\t" in value:
            raise ValueError("Project names must be a single line.")
        return value


class ProjectUpdate(ProjectInput):
    expected_generation: int = Field(ge=1, strict=True)
