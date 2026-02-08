from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4
from unittest.mock import MagicMock

import httpx
import pytest

from app.config import WorkerSettings
from app.repository import SupabaseWorkerRepository


def _settings() -> WorkerSettings:
    return WorkerSettings(
        supabase_url="https://example.supabase.co",
        supabase_service_role_key="service-role-key",
        mailjet_api_key="mailjet-api-key",
        mailjet_api_secret="mailjet-api-secret",
        mailjet_from_email="noreply@example.com",
    )


@pytest.mark.asyncio
async def test_claim_due_requests_uses_rpc_and_parses_rows() -> None:
    request_id = uuid4()
    lock_token = uuid4()
    audio_id = uuid4()

    client = MagicMock()
    rpc_result = MagicMock()
    rpc_result.execute.return_value = SimpleNamespace(
        data=[
            {
                "id": str(request_id),
                "email": "user@example.com",
                "audio_id": str(audio_id),
                "transcript_id": None,
                "raw_transcript": None,
                "lock_token": str(lock_token),
                "attempts": 1,
            }
        ]
    )
    client.rpc.return_value = rpc_result

    repo = SupabaseWorkerRepository(_settings(), client=client)
    claimed = await repo.claim_due_requests(10)

    client.rpc.assert_called_once_with("claim_due_requests", {"batch_size": 10})
    assert len(claimed) == 1
    assert claimed[0].id == request_id
    assert claimed[0].lock_token == lock_token
    assert claimed[0].audio_id == audio_id
    assert claimed[0].attempts == 1


@pytest.mark.asyncio
async def test_claim_due_requests_returns_empty_after_transport_failures(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = MagicMock()
    rpc_result = MagicMock()
    rpc_result.execute.side_effect = httpx.RemoteProtocolError("Server disconnected")
    client.rpc.return_value = rpc_result

    monkeypatch.setattr("app.repository.create_client", lambda *_args, **_kwargs: client)

    settings = WorkerSettings(
        supabase_url="https://example.supabase.co",
        supabase_service_role_key="service-role-key",
        mailjet_api_key="mailjet-api-key",
        mailjet_api_secret="mailjet-api-secret",
        mailjet_from_email="noreply@example.com",
        supabase_claim_retries=2,
        supabase_claim_retry_base_seconds=0.1,
    )
    repo = SupabaseWorkerRepository(settings, client=client)
    claimed = await repo.claim_due_requests(10)

    assert claimed == []
    assert client.rpc.call_count == 2
