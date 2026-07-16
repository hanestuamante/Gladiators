from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator


class SourceLocator(BaseModel):
    kind: Literal["url", "file", "api", "internal"]
    value: str = Field(min_length=1)

    @field_validator("value")
    @classmethod
    def validate_url(cls, value: str, info):
        if info.data.get("kind") == "url" and not value.startswith(("https://", "http://")):
            raise ValueError("URL locator phải bắt đầu bằng http:// hoặc https://")
        return value


class ExternalRecord(BaseModel):
    source_locator: SourceLocator
    retrieved_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    content_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    license: str | None = None
    payload: dict[str, Any]

