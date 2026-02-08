from __future__ import annotations

from functools import lru_cache

from pydantic import AliasChoices, Field, field_validator, model_validator
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

    mailjet_api_key: str = Field(validation_alias=AliasChoices("MAILJET_API_KEY", "MJ_APIKEY_PUBLIC"))
    mailjet_api_secret: str = Field(validation_alias=AliasChoices("MAILJET_API_SECRET", "MJ_APIKEY_PRIVATE"))
    mailjet_base_url: str = "https://api.mailjet.com"
    mailjet_from_email: str
    mailjet_from_name: str = "Voice Agent"
    mailjet_timeout_seconds: int = 20

    email_subject: str = "Your conversation summary"
    email_reply_to: str | None = None
    summarizer_max_bullets: int = Field(default=5, ge=3, le=5)

    @field_validator(
        "mailjet_api_key",
        "mailjet_api_secret",
        "mailjet_base_url",
        "mailjet_from_email",
        "mailjet_from_name",
        "email_subject",
        "email_reply_to",
        mode="before",
    )
    @classmethod
    def _strip_env_strings(cls, value: object) -> object:
        if isinstance(value, str):
            trimmed = value.strip()
            return trimmed or None
        return value

    @model_validator(mode="after")
    def _validate_mailjet_credentials(self) -> WorkerSettings:
        if self.mailjet_api_key == self.mailjet_api_secret:
            raise ValueError("MAILJET_API_KEY and MAILJET_API_SECRET must be different values")
        return self


@lru_cache(maxsize=1)
def get_settings() -> WorkerSettings:
    return WorkerSettings()
