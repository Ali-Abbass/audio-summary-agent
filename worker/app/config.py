from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class WorkerSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env", "../.env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    log_level: str = "INFO"

    supabase_url: str
    supabase_service_role_key: str
    supabase_storage_bucket: str = "voice-audio"

    worker_poll_seconds: float = 2.0
    worker_batch_size: int = 10
    worker_max_attempts: int = 3
    supabase_claim_retries: int = 3
    supabase_claim_retry_base_seconds: float = 0.5

    whisper_model_size: str = "small"

    mailjet_api_key: str
    mailjet_api_secret: str
    mailjet_base_url: str = "https://api.mailjet.com"
    mailjet_from_email: str
    mailjet_from_name: str = "Voice Agent"
    mailjet_timeout_seconds: int = 20

    email_subject: str = "Your conversation summary"
    email_reply_to: str | None = None
    summarizer_max_bullets: int = Field(default=5, ge=3, le=5)


@lru_cache(maxsize=1)
def get_settings() -> WorkerSettings:
    return WorkerSettings()
