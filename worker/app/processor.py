from __future__ import annotations

from pathlib import Path
from time import perf_counter
from uuid import UUID

import anyio
import structlog

from app.config import WorkerSettings
from app.emailer import MailjetEmailSender
from app.repository import SupabaseWorkerRepository
from app.summarizer import DeterministicSummarizer
from app.transcriber import WhisperTranscriber
from app.types import ClaimedRequest

logger = structlog.get_logger(__name__)


class WorkerProcessor:
    def __init__(
        self,
        *,
        settings: WorkerSettings,
        repository: SupabaseWorkerRepository,
        transcriber: WhisperTranscriber,
        summarizer: DeterministicSummarizer,
        emailer: MailjetEmailSender,
    ) -> None:
        self._settings = settings
        self._repository = repository
        self._transcriber = transcriber
        self._summarizer = summarizer
        self._emailer = emailer

    async def run_forever(self) -> None:
        logger.info("worker_started", poll_seconds=self._settings.worker_poll_seconds)
        while True:
            cycle_started = perf_counter()
            try:
                await self.process_once()
            except Exception as exc:
                logger.exception("worker_cycle_failed", error=str(exc))
            logger.info("worker_cycle_done", duration_ms=round((perf_counter() - cycle_started) * 1000, 2))
            await anyio.sleep(self._settings.worker_poll_seconds)

    async def process_once(self) -> None:
        claim_started = perf_counter()
        claims = await self._repository.claim_due_requests(self._settings.worker_batch_size)
        logger.info(
            "claimed_due_requests",
            count=len(claims),
            duration_ms=round((perf_counter() - claim_started) * 1000, 2),
        )

        for claim in claims:
            await self._process_claim(claim)

    async def _process_claim(self, claim: ClaimedRequest) -> None:
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(request_id=str(claim.id), job_id=str(claim.id))

        started = perf_counter()
        email_attempted = False
        try:
            transcript_text, transcript_id = await self._resolve_transcript(claim)

            summary_started = perf_counter()
            summary = self._summarizer.summarize(transcript_text)
            logger.info(
                "summary_generated",
                duration_ms=round((perf_counter() - summary_started) * 1000, 2),
                bullet_count=len(summary.get("bullets", [])),
            )

            email_started = perf_counter()
            email_attempted = True
            send_result = await anyio.to_thread.run_sync(
                self._emailer.send_summary_email,
                claim.email,
                summary,
                str(claim.id),
            )
            logger.info(
                "email_sent",
                message_id=send_result.message_id,
                provider_status=send_result.provider_status,
                recipient_state=send_result.recipient_state,
                message_href=send_result.message_href,
                duration_ms=round((perf_counter() - email_started) * 1000, 2),
            )

            await self._repository.insert_email_delivery(
                request_id=claim.id,
                provider=self._emailer.provider,
                status="sent",
                message_id=send_result.message_id,
                error=None,
            )

            await self._repository.mark_sent(
                request_id=claim.id,
                lock_token=claim.lock_token,
                transcript_id=transcript_id,
                transcript_text=transcript_text,
                summary_json=summary,
            )

            logger.info(
                "request_completed",
                status="sent",
                attempts=claim.attempts,
                duration_ms=round((perf_counter() - started) * 1000, 2),
            )
        except Exception as exc:
            error_message = str(exc)
            logger.exception(
                "request_failed",
                error=error_message,
                attempts=claim.attempts,
                duration_ms=round((perf_counter() - started) * 1000, 2),
            )
            if email_attempted:
                try:
                    await self._repository.insert_email_delivery(
                        request_id=claim.id,
                        provider=self._emailer.provider,
                        status="failed",
                        message_id=None,
                        error=error_message,
                    )
                except Exception:
                    logger.exception("email_delivery_failure_record_failed")

            await self._repository.handle_failure(
                request_id=claim.id,
                lock_token=claim.lock_token,
                attempts=claim.attempts,
                error_message=error_message,
                max_attempts=self._settings.worker_max_attempts,
            )
        finally:
            structlog.contextvars.clear_contextvars()

    async def _resolve_transcript(self, claim: ClaimedRequest) -> tuple[str, UUID | None]:
        if claim.raw_transcript and claim.raw_transcript.strip():
            logger.info("using_raw_transcript")
            return claim.raw_transcript.strip(), claim.transcript_id

        if claim.transcript_id:
            transcript_started = perf_counter()
            existing = await self._repository.get_transcript_text(claim.transcript_id)
            logger.info(
                "loaded_existing_transcript",
                duration_ms=round((perf_counter() - transcript_started) * 1000, 2),
            )
            if existing and existing.strip():
                return existing.strip(), claim.transcript_id

        if claim.audio_id is None:
            raise RuntimeError("No transcript or audio reference available")

        asset_started = perf_counter()
        asset = await self._repository.get_audio_asset(claim.audio_id)
        if not asset or not asset.get("storage_path"):
            raise RuntimeError("Audio asset not found or missing storage_path")
        logger.info("loaded_audio_asset", duration_ms=round((perf_counter() - asset_started) * 1000, 2))

        download_started = perf_counter()
        storage_path = str(asset["storage_path"])
        audio_bytes = await self._repository.download_audio_bytes(storage_path)
        logger.info(
            "downloaded_audio",
            bytes=len(audio_bytes),
            duration_ms=round((perf_counter() - download_started) * 1000, 2),
        )

        transcribe_started = perf_counter()
        suffix = Path(storage_path).suffix or ".webm"
        transcript_text = await anyio.to_thread.run_sync(
            self._transcriber.transcribe_bytes,
            audio_bytes,
            suffix,
        )
        if not transcript_text.strip():
            raise RuntimeError("Transcriber returned empty transcript")
        logger.info(
            "audio_transcribed",
            provider=self._transcriber.provider,
            duration_ms=round((perf_counter() - transcribe_started) * 1000, 2),
        )

        save_started = perf_counter()
        transcript_id = await self._repository.insert_transcript(
            audio_id=claim.audio_id,
            text=transcript_text,
            provider=self._transcriber.provider,
        )
        logger.info("transcript_saved", duration_ms=round((perf_counter() - save_started) * 1000, 2))
        return transcript_text, transcript_id
