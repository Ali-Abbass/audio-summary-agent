from __future__ import annotations

from datetime import datetime, timezone
from functools import partial
from typing import Any, Protocol
from uuid import UUID, uuid4

import anyio
from supabase import Client, create_client

from app.config import Settings


class SummaryRepository(Protocol):
    async def check_ready(self) -> None: ...

    async def create_audio_asset(self, *, data: bytes, content_type: str) -> UUID: ...

    async def create_summary_request(
        self,
        *,
        email: str,
        audio_id: UUID,
        send_at: datetime,
    ) -> dict[str, Any]: ...

    async def get_summary_request(self, request_id: UUID) -> dict[str, Any] | None: ...


class SupabaseRepository:
    _audio_extensions = {
        "audio/webm": ".webm",
        "audio/ogg": ".ogg",
        "audio/wav": ".wav",
        "audio/mpeg": ".mp3",
    }

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._client: Client = create_client(settings.supabase_url, settings.supabase_service_role_key)

    async def _run(self, fn, *args, **kwargs):  # type: ignore[no-untyped-def]
        call = partial(fn, *args, **kwargs)
        return await anyio.to_thread.run_sync(call)

    async def check_ready(self) -> None:
        await self._run(self._check_ready_sync)

    def _check_ready_sync(self) -> None:
        self._client.table("summary_requests").select("id").limit(1).execute()

    async def create_audio_asset(self, *, data: bytes, content_type: str) -> UUID:
        return await self._run(self._create_audio_asset_sync, data, content_type)

    def _create_audio_asset_sync(self, data: bytes, content_type: str) -> UUID:
        audio_id = uuid4()
        extension = self._audio_extensions.get(content_type, ".bin")
        date_prefix = datetime.now(timezone.utc).strftime("%Y/%m/%d")
        storage_path = f"{date_prefix}/{audio_id}{extension}"

        self._client.storage.from_(self._settings.supabase_storage_bucket).upload(
            storage_path,
            data,
            {"content-type": content_type, "upsert": False},
        )

        result = (
            self._client.table("audio_assets")
            .insert(
                {
                    "id": str(audio_id),
                    "storage_path": storage_path,
                    "content_type": content_type,
                }
            )
            .execute()
        )
        if not result.data:
            raise RuntimeError("audio_assets insert failed")

        return audio_id

    async def create_summary_request(
        self,
        *,
        email: str,
        audio_id: UUID,
        send_at: datetime,
    ) -> dict[str, Any]:
        return await self._run(self._create_summary_request_sync, email, audio_id, send_at)

    def _create_summary_request_sync(
        self,
        email: str,
        audio_id: UUID,
        send_at: datetime,
    ) -> dict[str, Any]:
        payload = {
            "email": email,
            "audio_id": str(audio_id),
            "send_at": send_at.astimezone(timezone.utc).isoformat(),
            "status": "pending",
        }
        result = self._client.table("summary_requests").insert(payload).execute()
        data = result.data
        if not data:
            raise RuntimeError("summary_requests insert failed")
        row = data[0] if isinstance(data, list) else data
        return {
            "id": row["id"],
            "status": row["status"],
            "send_at": row["send_at"],
        }

    async def get_summary_request(self, request_id: UUID) -> dict[str, Any] | None:
        return await self._run(self._get_summary_request_sync, request_id)

    def _get_summary_request_sync(self, request_id: UUID) -> dict[str, Any] | None:
        result = (
            self._client.table("summary_requests")
            .select("id,status,send_at,attempts,last_error,summary_json,transcript_text")
            .eq("id", str(request_id))
            .limit(1)
            .execute()
        )
        if not result.data:
            return None
        return result.data[0]
