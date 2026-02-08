from __future__ import annotations

from datetime import datetime, timezone
from time import perf_counter
from typing import Any
from uuid import UUID

import structlog
from fastapi import Depends, FastAPI, Request, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import Settings, get_settings
from app.errors import APIError, register_exception_handlers
from app.logging_setup import configure_logging
from app.middleware import RequestIDMiddleware
from app.repository import SupabaseRepository, SummaryRepository
from app.schemas import (
    AudioUploadResponse,
    CreateSummaryRequestInput,
    CreateSummaryRequestResponse,
    RequestStatusResponse,
    SummaryPayload,
)

logger = structlog.get_logger(__name__)

ALLOWED_AUDIO_TYPES = {"audio/webm", "audio/ogg", "audio/wav", "audio/mpeg"}


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(service="backend", level=settings.log_level)

    app = FastAPI(title=settings.app_name)
    app.state.settings = settings
    app.state.repository = SupabaseRepository(settings)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["X-Request-ID"],
    )
    app.add_middleware(RequestIDMiddleware)
    register_exception_handlers(app)

    @app.get("/healthz")
    async def healthz() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/readyz")
    async def readyz(repo: SummaryRepository = Depends(get_repository)) -> JSONResponse:
        started = perf_counter()
        try:
            await repo.check_ready()
        except Exception as exc:
            logger.exception("readyz_failed", error=str(exc))
            raise APIError(
                code="DEPENDENCY_UNAVAILABLE",
                message="Supabase check failed",
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            ) from exc

        logger.info("readyz_ok", duration_ms=round((perf_counter() - started) * 1000, 2))
        return JSONResponse(status_code=status.HTTP_200_OK, content={"status": "ready"})

    @app.post("/v1/audio", response_model=AudioUploadResponse, status_code=status.HTTP_201_CREATED)
    async def create_audio(
        file: UploadFile,
        repo: SummaryRepository = Depends(get_repository),
        settings: Settings = Depends(get_app_settings),
    ) -> AudioUploadResponse:
        raw_content_type = (file.content_type or "").lower().strip()
        content_type = raw_content_type.split(";", 1)[0].strip()
        if content_type not in ALLOWED_AUDIO_TYPES:
            raise APIError(
                code="UNSUPPORTED_MEDIA_TYPE",
                message=f"Unsupported content type: {raw_content_type or 'unknown'}",
                status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            )

        max_bytes = settings.max_audio_mb * 1024 * 1024
        read_started = perf_counter()
        data = await file.read(max_bytes + 1)
        read_duration = round((perf_counter() - read_started) * 1000, 2)

        if not data:
            raise APIError(code="EMPTY_FILE", message="Audio file is empty", status_code=status.HTTP_400_BAD_REQUEST)
        if len(data) > max_bytes:
            raise APIError(
                code="PAYLOAD_TOO_LARGE",
                message=f"Audio exceeds {settings.max_audio_mb} MB limit",
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            )

        insert_started = perf_counter()
        audio_id = await repo.create_audio_asset(data=data, content_type=content_type)
        insert_duration = round((perf_counter() - insert_started) * 1000, 2)

        logger.info(
            "audio_uploaded",
            audio_id=str(audio_id),
            content_type=content_type,
            raw_content_type=raw_content_type,
            size_bytes=len(data),
            read_duration_ms=read_duration,
            upload_duration_ms=insert_duration,
        )
        return AudioUploadResponse(audio_id=audio_id)

    @app.post("/v1/requests", response_model=CreateSummaryRequestResponse, status_code=status.HTTP_201_CREATED)
    async def create_request(
        payload: CreateSummaryRequestInput,
        repo: SummaryRepository = Depends(get_repository),
    ) -> CreateSummaryRequestResponse:
        send_at = payload.send_at or datetime.now(timezone.utc)
        start = perf_counter()
        record = await repo.create_summary_request(email=payload.email, audio_id=payload.audio_id, send_at=send_at)
        logger.info(
            "summary_request_created",
            request_id=record["id"],
            email=payload.email,
            duration_ms=round((perf_counter() - start) * 1000, 2),
        )
        return CreateSummaryRequestResponse(
            request_id=record["id"],
            status=record["status"],
            send_at=record["send_at"],
        )

    @app.get("/v1/requests/{request_id}", response_model=RequestStatusResponse)
    async def get_request(
        request_id: UUID,
        repo: SummaryRepository = Depends(get_repository),
    ) -> RequestStatusResponse:
        start = perf_counter()
        record = await repo.get_summary_request(request_id)
        if record is None:
            raise APIError(code="NOT_FOUND", message="Summary request not found", status_code=status.HTTP_404_NOT_FOUND)

        summary: SummaryPayload | None = None
        summary_data: Any = record.get("summary_json")
        if summary_data:
            summary = SummaryPayload.model_validate(summary_data)

        logger.info(
            "summary_request_fetched",
            request_id=str(request_id),
            status=record["status"],
            duration_ms=round((perf_counter() - start) * 1000, 2),
        )

        return RequestStatusResponse(
            request_id=record["id"],
            status=record["status"],
            send_at=record["send_at"],
            attempts=record["attempts"],
            last_error=record.get("last_error"),
            summary=summary,
            transcript_text=record.get("transcript_text"),
        )

    return app


def get_app_settings(request: Request) -> Settings:
    return request.app.state.settings


def get_repository(request: Request) -> SummaryRepository:
    return request.app.state.repository


app = create_app()
