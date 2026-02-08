from __future__ import annotations

from datetime import datetime, timedelta, timezone
from functools import partial
import time
from typing import Any
from uuid import UUID

import anyio
import httpx
import structlog
from supabase import Client, create_client

from app.config import WorkerSettings
from app.types import ClaimedRequest

logger = structlog.get_logger(__name__)


class SupabaseWorkerRepository:
    def __init__(self, settings: WorkerSettings, client: Client | None = None) -> None:
        self._settings = settings
        self._client: Client = client or create_client(settings.supabase_url, settings.supabase_service_role_key)

    async def _run(self, fn, *args, **kwargs):  # type: ignore[no-untyped-def]
        call = partial(fn, *args, **kwargs)
        return await anyio.to_thread.run_sync(call)

    async def claim_due_requests(self, batch_size: int) -> list[ClaimedRequest]:
        return await self._run(self._claim_due_requests_sync, batch_size)

    def _claim_due_requests_sync(self, batch_size: int) -> list[ClaimedRequest]:
        max_retries = max(1, self._settings.supabase_claim_retries)
        base_delay = max(0.1, self._settings.supabase_claim_retry_base_seconds)

        for attempt in range(1, max_retries + 1):
            try:
                result = self._client.rpc("claim_due_requests", {"batch_size": batch_size}).execute()
                rows = result.data or []
                claimed: list[ClaimedRequest] = []
                for row in rows:
                    claimed.append(
                        ClaimedRequest(
                            id=UUID(row["id"]),
                            email=row["email"],
                            audio_id=UUID(row["audio_id"]) if row.get("audio_id") else None,
                            transcript_id=UUID(row["transcript_id"]) if row.get("transcript_id") else None,
                            raw_transcript=row.get("raw_transcript"),
                            lock_token=UUID(row["lock_token"]),
                            attempts=int(row["attempts"]),
                        )
                    )
                return claimed
            except (httpx.TransportError, httpx.TimeoutException) as exc:
                if attempt >= max_retries:
                    logger.warning(
                        "claim_due_requests_transport_unavailable",
                        attempt=attempt,
                        max_retries=max_retries,
                        error=str(exc),
                    )
                    return []

                # Refresh client to avoid reusing a broken connection.
                self._client = create_client(
                    self._settings.supabase_url,
                    self._settings.supabase_service_role_key,
                )
                time.sleep(base_delay * (2 ** (attempt - 1)))

        return []

    async def get_transcript_text(self, transcript_id: UUID) -> str | None:
        return await self._run(self._get_transcript_text_sync, transcript_id)

    def _get_transcript_text_sync(self, transcript_id: UUID) -> str | None:
        result = (
            self._client.table("transcripts")
            .select("text")
            .eq("id", str(transcript_id))
            .limit(1)
            .execute()
        )
        if not result.data:
            return None
        return result.data[0]["text"]

    async def get_audio_asset(self, audio_id: UUID) -> dict[str, Any] | None:
        return await self._run(self._get_audio_asset_sync, audio_id)

    def _get_audio_asset_sync(self, audio_id: UUID) -> dict[str, Any] | None:
        result = (
            self._client.table("audio_assets")
            .select("storage_path,content_type")
            .eq("id", str(audio_id))
            .limit(1)
            .execute()
        )
        if not result.data:
            return None
        return result.data[0]

    async def download_audio_bytes(self, storage_path: str) -> bytes:
        return await self._run(self._download_audio_bytes_sync, storage_path)

    def _download_audio_bytes_sync(self, storage_path: str) -> bytes:
        data = self._client.storage.from_(self._settings.supabase_storage_bucket).download(storage_path)
        if not data:
            raise RuntimeError("Downloaded audio is empty")
        return data

    async def insert_transcript(self, *, audio_id: UUID, text: str, provider: str) -> UUID:
        return await self._run(self._insert_transcript_sync, audio_id, text, provider)

    def _insert_transcript_sync(self, audio_id: UUID, text: str, provider: str) -> UUID:
        result = self._client.table("transcripts").insert(
            {"audio_id": str(audio_id), "text": text, "provider": provider}
        ).execute()
        data = result.data
        if not data:
            raise RuntimeError("Failed to insert transcript")
        row = data[0] if isinstance(data, list) else data
        return UUID(row["id"])

    async def mark_sent(
        self,
        *,
        request_id: UUID,
        lock_token: UUID,
        transcript_id: UUID | None,
        transcript_text: str,
        summary_json: dict[str, Any],
    ) -> None:
        await self._run(
            self._mark_sent_sync,
            request_id,
            lock_token,
            transcript_id,
            transcript_text,
            summary_json,
        )

    def _mark_sent_sync(
        self,
        request_id: UUID,
        lock_token: UUID,
        transcript_id: UUID | None,
        transcript_text: str,
        summary_json: dict[str, Any],
    ) -> None:
        payload = {
            "status": "sent",
            "transcript_id": str(transcript_id) if transcript_id else None,
            "transcript_text": transcript_text,
            "summary_json": summary_json,
            "last_error": None,
            "locked_at": None,
            "lock_token": None,
        }
        (
            self._client.table("summary_requests")
            .update(payload)
            .eq("id", str(request_id))
            .eq("lock_token", str(lock_token))
            .execute()
        )

    async def insert_email_delivery(
        self,
        *,
        request_id: UUID,
        provider: str,
        status: str,
        message_id: str | None,
        error: str | None,
    ) -> None:
        await self._run(
            self._insert_email_delivery_sync,
            request_id,
            provider,
            status,
            message_id,
            error,
        )

    def _insert_email_delivery_sync(
        self,
        request_id: UUID,
        provider: str,
        status: str,
        message_id: str | None,
        error: str | None,
    ) -> None:
        payload = {
            "request_id": str(request_id),
            "provider": provider,
            "status": status,
            "message_id": message_id,
            "error": error,
            "sent_at": datetime.now(timezone.utc).isoformat() if status == "sent" else None,
        }
        self._client.table("email_deliveries").insert(payload).execute()

    async def handle_failure(
        self,
        *,
        request_id: UUID,
        lock_token: UUID,
        attempts: int,
        error_message: str,
        max_attempts: int,
    ) -> None:
        await self._run(
            self._handle_failure_sync,
            request_id,
            lock_token,
            attempts,
            error_message,
            max_attempts,
        )

    def _handle_failure_sync(
        self,
        request_id: UUID,
        lock_token: UUID,
        attempts: int,
        error_message: str,
        max_attempts: int,
    ) -> None:
        safe_error = error_message[:2000]
        if attempts < max_attempts:
            retry_time = datetime.now(timezone.utc) + timedelta(minutes=(2**attempts))
            payload = {
                "status": "pending",
                "send_at": retry_time.isoformat(),
                "last_error": safe_error,
                "locked_at": None,
                "lock_token": None,
            }
        else:
            payload = {
                "status": "failed",
                "last_error": safe_error,
                "locked_at": None,
                "lock_token": None,
            }

        (
            self._client.table("summary_requests")
            .update(payload)
            .eq("id", str(request_id))
            .eq("lock_token", str(lock_token))
            .execute()
        )
