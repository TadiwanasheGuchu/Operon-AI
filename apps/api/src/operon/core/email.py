"""Outbound email. Console in development, SMTP or Brevo's HTTPS API in deployed environments
(the API for hosts that block SMTP ports), memory in tests."""

import asyncio
import smtplib
from dataclasses import dataclass
from email.message import EmailMessage as MimeMessage
from email.utils import parseaddr
from typing import Protocol

import httpx

from operon.core.config import Settings
from operon.core.logging import get_logger

log = get_logger(__name__)


@dataclass(frozen=True)
class EmailMessage:
    to: str
    subject: str
    text: str


class EmailSender(Protocol):
    async def send(self, message: EmailMessage) -> None: ...


class ConsoleEmailSender:
    """Development only: prints the message (including links) to the API log."""

    async def send(self, message: EmailMessage) -> None:
        log.info("email_console", to=message.to, subject=message.subject, body=message.text)


class MemoryEmailSender:
    def __init__(self) -> None:
        self.outbox: list[EmailMessage] = []

    async def send(self, message: EmailMessage) -> None:
        self.outbox.append(message)


class SmtpEmailSender:
    def __init__(self, settings: Settings) -> None:
        self._s = settings

    def _send_sync(self, message: EmailMessage) -> None:
        mime = MimeMessage()
        mime["From"] = self._s.email_from
        mime["To"] = message.to
        mime["Subject"] = message.subject
        mime.set_content(message.text)
        with smtplib.SMTP(self._s.smtp_host, self._s.smtp_port, timeout=10) as smtp:
            if self._s.smtp_starttls:
                smtp.starttls()
            if self._s.smtp_username and self._s.smtp_password:
                smtp.login(self._s.smtp_username, self._s.smtp_password.get_secret_value())
            smtp.send_message(mime)

    async def send(self, message: EmailMessage) -> None:
        await asyncio.to_thread(self._send_sync, message)


class BrevoEmailSender:
    """Brevo transactional email over HTTPS (port 443)."""

    URL = "https://api.brevo.com/v3/smtp/email"

    def __init__(self, settings: Settings, client: httpx.AsyncClient | None = None) -> None:
        assert settings.brevo_api_key is not None
        self._key = settings.brevo_api_key.get_secret_value()
        name, address = parseaddr(settings.email_from)
        self._sender = {"email": address, **({"name": name} if name else {})}
        self._client = client

    async def send(self, message: EmailMessage) -> None:
        body = {
            "sender": self._sender,
            "to": [{"email": message.to}],
            "subject": message.subject,
            "textContent": message.text,
        }
        headers = {"api-key": self._key, "accept": "application/json"}
        if self._client is not None:
            response = await self._client.post(self.URL, json=body, headers=headers)
        else:
            async with httpx.AsyncClient(timeout=15) as client:
                response = await client.post(self.URL, json=body, headers=headers)
        if response.status_code >= 400:
            # Never log the key; Brevo's error body names the problem (e.g. unverified sender).
            log.warning("email_send_failed", provider="brevo", status=response.status_code)
            response.raise_for_status()


def create_email_sender(settings: Settings) -> EmailSender:
    if settings.email_backend == "brevo":
        return BrevoEmailSender(settings)
    if settings.email_backend == "smtp":
        return SmtpEmailSender(settings)
    if settings.email_backend == "memory":
        return MemoryEmailSender()
    return ConsoleEmailSender()
