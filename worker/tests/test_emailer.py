from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.config import WorkerSettings
from app.emailer import MailjetEmailSender


def _settings(**overrides: object) -> WorkerSettings:
    base: dict[str, object] = {
        "supabase_url": "https://example.supabase.co",
        "supabase_service_role_key": "service-role-key",
        "mailjet_api_key": "mailjet-public-key-1234",
        "mailjet_api_secret": "mailjet-secret-key-5678",
        "mailjet_from_email": "noreply@example.com",
    }
    base.update(overrides)
    return WorkerSettings(**base)


def test_send_summary_email_raises_helpful_error_on_401(monkeypatch: pytest.MonkeyPatch) -> None:
    sender = MailjetEmailSender(_settings())

    fake_response = SimpleNamespace(status_code=401, text='{"StatusCode":401}', json=lambda: {})
    monkeypatch.setattr("app.emailer.requests.post", lambda *args, **kwargs: fake_response)

    with pytest.raises(RuntimeError) as exc:
        sender.send_summary_email(
            recipient="user@example.com",
            summary={"bullets": ["one"], "next_step": "do it"},
            request_id="req-1",
        )

    message = str(exc.value)
    assert "Mailjet authentication failed (401)" in message
    assert "MAILJET_API_KEY/MAILJET_API_SECRET" in message
    assert "mail...1234" in message
    assert "mail...5678" in message


def test_send_summary_email_returns_message_metadata(monkeypatch: pytest.MonkeyPatch) -> None:
    sender = MailjetEmailSender(_settings())
    fake_body = {
        "Messages": [
            {
                "Status": "success",
                "To": [
                    {
                        "MessageID": 123456,
                        "MessageState": "accepted",
                        "MessageHref": "https://api.mailjet.com/v3/REST/message/123456",
                    }
                ],
            }
        ]
    }
    fake_response = SimpleNamespace(status_code=200, text="ok", json=lambda: fake_body)
    monkeypatch.setattr("app.emailer.requests.post", lambda *args, **kwargs: fake_response)

    result = sender.send_summary_email(
        recipient="user@example.com",
        summary={"bullets": ["one"], "next_step": "do it"},
        request_id="req-1",
    )

    assert result.message_id == "123456"
    assert result.provider_status == "success"
    assert result.recipient_state == "accepted"
    assert result.message_href == "https://api.mailjet.com/v3/REST/message/123456"


def test_settings_accept_mj_aliases_and_trim_values(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "service-role-key")
    monkeypatch.setenv("MJ_APIKEY_PUBLIC", "  public-key-1234  ")
    monkeypatch.setenv("MJ_APIKEY_PRIVATE", "  private-key-5678  ")
    monkeypatch.setenv("MAILJET_FROM_EMAIL", "  noreply@example.com  ")

    settings = WorkerSettings(_env_file=None)

    assert settings.mailjet_api_key == "public-key-1234"
    assert settings.mailjet_api_secret == "private-key-5678"
    assert settings.mailjet_from_email == "noreply@example.com"
