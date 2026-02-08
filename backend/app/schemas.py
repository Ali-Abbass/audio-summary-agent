from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field, field_validator


class AudioUploadResponse(BaseModel):
    audio_id: UUID


class CreateSummaryRequestInput(BaseModel):
    email: EmailStr
    audio_id: UUID
    send_at: datetime | None = None

    @field_validator("send_at")
    @classmethod
    def normalize_send_at(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            raise ValueError("send_at must include timezone information")
        return value.astimezone(timezone.utc)


class CreateSummaryRequestResponse(BaseModel):
    request_id: UUID
    status: str
    send_at: datetime


class SummaryPayload(BaseModel):
    bullets: list[str] = Field(min_length=3, max_length=5)
    next_step: str = Field(min_length=1, max_length=500)


class RequestStatusResponse(BaseModel):
    request_id: UUID
    status: str
    send_at: datetime
    attempts: int
    last_error: str | None = None
    summary: SummaryPayload | None = None
    transcript_text: str | None = None


class ErrorDetail(BaseModel):
    code: str
    message: str
    request_id: str


class ErrorEnvelope(BaseModel):
    error: ErrorDetail
