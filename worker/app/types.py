from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID


@dataclass(slots=True)
class ClaimedRequest:
    id: UUID
    email: str
    audio_id: UUID | None
    transcript_id: UUID | None
    raw_transcript: str | None
    lock_token: UUID
    attempts: int
