"""Browser inputs never supply system instructions, roles, grants or runtime IDs."""
from pydantic import BaseModel, ConfigDict, Field, field_validator
import unicodedata
from typing import Literal


class ChatInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True, hide_input_in_errors=True)
    message: str = Field(min_length=1, max_length=4000)
    model: str = Field(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9][A-Za-z0-9_./:@+-]*$")
    idempotency_key: str = Field(min_length=16, max_length=128, pattern=r"^[A-Za-z0-9_-]+$")
    expected_revision: int = Field(default=0, ge=0, strict=True)
    # Legacy wire compatibility only; signed Core consent receipts authorize transfer.
    allow_remote_model: bool = Field(default=False, strict=True)


class ConsentInput(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)
    model: str = Field(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9][A-Za-z0-9_./:@+-]*$")
    policy: str = Field(pattern=r"^[a-f0-9]{64}$")


class PreferenceInput(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)
    locale: Literal["id-ID", "en-US"]


class ConversationDeleteInput(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)
    idempotency_key: str = Field(min_length=16, max_length=128, pattern=r"^[A-Za-z0-9_-]+$")
    expected_metadata_revision: int = Field(ge=0, strict=True)


class ConversationRenameInput(ConversationDeleteInput):
    title: str = Field(min_length=1, max_length=120, strict=True)

    @field_validator("title", mode="before")
    @classmethod
    def plain_title(cls, value):
        if isinstance(value, str):
            if any(unicodedata.category(char) in {"Cc", "Cf"} for char in value):
                raise ValueError("Title must be a single line without control characters.")
            return value.strip()
        return value
