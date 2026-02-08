from __future__ import annotations

import anyio

from app.config import get_settings
from app.emailer import MailjetEmailSender
from app.logging_setup import configure_logging
from app.processor import WorkerProcessor
from app.repository import SupabaseWorkerRepository
from app.summarizer import DeterministicSummarizer
from app.transcriber import WhisperTranscriber


async def _main() -> None:
    settings = get_settings()
    configure_logging(service="worker", level=settings.log_level)

    processor = WorkerProcessor(
        settings=settings,
        repository=SupabaseWorkerRepository(settings),
        transcriber=WhisperTranscriber(model_size=settings.whisper_model_size),
        summarizer=DeterministicSummarizer(max_bullets=settings.summarizer_max_bullets),
        emailer=MailjetEmailSender(settings),
    )
    await processor.run_forever()


if __name__ == "__main__":
    anyio.run(_main)
