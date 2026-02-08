from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID, uuid4

import pytest

from app.config import get_settings
from app.main import create_app


class FakeRepository:
    def __init__(self) -> None:
        self.requests: dict[str, dict] = {}

    async def check_ready(self) -> None:
        return None

    async def create_audio_asset(self, *, data: bytes, content_type: str) -> UUID:
        return uuid4()

    async def create_summary_request(self, *, email: str, audio_id: UUID, send_at: datetime) -> dict:
        request_id = uuid4()
        row = {
            "id": str(request_id),
            "status": "pending",
            "send_at": send_at.astimezone(timezone.utc).isoformat(),
            "attempts": 0,
            "last_error": None,
            "summary_json": None,
            "transcript_text": None,
        }
        self.requests[str(request_id)] = row
        return {"id": str(request_id), "status": "pending", "send_at": row["send_at"]}

    async def get_summary_request(self, request_id: UUID) -> dict | None:
        return self.requests.get(str(request_id))


@pytest.fixture()
def test_app(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "dummy")
    monkeypatch.setenv("MAX_AUDIO_MB", "1")
    get_settings.cache_clear()

    app = create_app()
    fake_repo = FakeRepository()
    app.state.repository = fake_repo
    return app
