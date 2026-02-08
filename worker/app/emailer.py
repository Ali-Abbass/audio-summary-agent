from __future__ import annotations

import html
from dataclasses import dataclass
from typing import Any

import requests

from app.config import WorkerSettings


@dataclass(frozen=True)
class EmailSendResult:
    message_id: str
    provider_status: str
    message_href: str | None
    recipient_state: str | None


class MailjetEmailSender:
    provider = "mailjet"

    def __init__(self, settings: WorkerSettings) -> None:
        self._settings = settings

    @staticmethod
    def _mask_secret(value: str) -> str:
        if len(value) <= 8:
            return "*" * len(value)
        return f"{value[:4]}...{value[-4:]}"

    def send_summary_email(
        self,
        recipient: str,
        summary: dict[str, object],
        request_id: str | None = None,
    ) -> EmailSendResult:
        bullets = [str(item) for item in summary.get("bullets", [])]
        next_step = str(summary.get("next_step", ""))

        text_lines = ["Your conversation summary", "", "Key points:"]
        text_lines.extend(f"- {bullet}" for bullet in bullets)
        text_lines.extend(["", f"Next step: {next_step}"])
        text_part = "\n".join(text_lines)

        html_bullets = "".join(f"<li>{html.escape(bullet)}</li>" for bullet in bullets)
        html_part = (
            "<html><body>"
            "<h2>Your conversation summary</h2>"
            "<p><strong>Key points:</strong></p>"
            f"<ul>{html_bullets}</ul>"
            f"<p><strong>Next step:</strong> {html.escape(next_step)}</p>"
            "</body></html>"
        )

        message: dict[str, Any] = {
            "From": {
                "Email": self._settings.mailjet_from_email,
                "Name": self._settings.mailjet_from_name,
            },
            "To": [{"Email": recipient}],
            "Subject": self._settings.email_subject,
            "TextPart": text_part,
            "HTMLPart": html_part,
        }
        if request_id:
            message["CustomID"] = request_id
        if self._settings.email_reply_to:
            message["ReplyTo"] = {"Email": self._settings.email_reply_to}

        payload = {"Messages": [message]}
        url = f"{self._settings.mailjet_base_url.rstrip('/')}/v3.1/send"

        try:
            response = requests.post(
                url,
                auth=(self._settings.mailjet_api_key, self._settings.mailjet_api_secret),
                json=payload,
                timeout=self._settings.mailjet_timeout_seconds,
            )
        except requests.RequestException as exc:
            raise RuntimeError(f"Mailjet transport failure: {exc}") from exc
        if response.status_code >= 400:
            if response.status_code == 401:
                key_hint = self._mask_secret(self._settings.mailjet_api_key)
                secret_hint = self._mask_secret(self._settings.mailjet_api_secret)
                raise RuntimeError(
                    "Mailjet authentication failed (401). "
                    "Verify MAILJET_API_KEY/MAILJET_API_SECRET are active Send API keys "
                    "(not SMTP credentials), belong to the same account, and contain no whitespace. "
                    f"key={key_hint}, secret={secret_hint}"
                )
            raise RuntimeError(
                f"Mailjet send failed with status {response.status_code}: {response.text[:400]}"
            )

        try:
            body = response.json()
        except ValueError as exc:
            raise RuntimeError(f"Mailjet returned non-JSON response: {response.text[:400]}") from exc

        sent = (body.get("Messages") or [{}])[0]
        provider_status = str(sent.get("Status") or "unknown").lower()
        if provider_status != "success":
            raise RuntimeError(f"Mailjet returned non-success status: {provider_status}; body={sent}")

        errors = sent.get("Errors") or []
        if errors:
            raise RuntimeError(f"Mailjet send returned errors: {errors}")

        recipient_status = (sent.get("To") or [{}])[0]
        message_id = recipient_status.get("MessageID") or recipient_status.get("MessageUUID")
        if message_id is None:
            raise RuntimeError("Mailjet response missing message identifier")
        return EmailSendResult(
            message_id=str(message_id),
            provider_status=provider_status,
            message_href=recipient_status.get("MessageHref"),
            recipient_state=recipient_status.get("MessageState"),
        )
