from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient


@pytest.mark.asyncio
async def test_healthz(test_app) -> None:
    async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as client:
        response = await client.get("/healthz")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


@pytest.mark.asyncio
async def test_upload_audio_success(test_app) -> None:
    async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as client:
        response = await client.post(
            "/v1/audio",
            files={"file": ("recording.webm", b"abc123", "audio/webm")},
        )

    assert response.status_code == 201
    assert "audio_id" in response.json()


@pytest.mark.asyncio
async def test_upload_audio_accepts_webm_with_codec_parameter(test_app) -> None:
    async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as client:
        response = await client.post(
            "/v1/audio",
            files={"file": ("recording.webm", b"abc123", "audio/webm;codecs=opus")},
        )

    assert response.status_code == 201
    assert "audio_id" in response.json()


@pytest.mark.asyncio
async def test_upload_audio_rejects_invalid_type(test_app) -> None:
    async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as client:
        response = await client.post(
            "/v1/audio",
            files={"file": ("recording.txt", b"abc123", "text/plain")},
        )

    assert response.status_code == 415
    body = response.json()
    assert body["error"]["code"] == "UNSUPPORTED_MEDIA_TYPE"


@pytest.mark.asyncio
async def test_create_request_and_fetch_status(test_app) -> None:
    send_at = datetime.now(timezone.utc).isoformat()

    async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as client:
        create_response = await client.post(
            "/v1/requests",
            json={"email": "user@example.com", "audio_id": str(uuid4()), "send_at": send_at},
        )
        request_id = create_response.json()["request_id"]

        status_response = await client.get(f"/v1/requests/{request_id}")

    assert create_response.status_code == 201
    assert status_response.status_code == 200
    assert status_response.json()["status"] == "pending"


@pytest.mark.asyncio
async def test_invalid_email_validation_error(test_app) -> None:
    async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as client:
        response = await client.post("/v1/requests", json={"email": "not-an-email", "audio_id": "11111111-1111-1111-1111-111111111111"})

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"
