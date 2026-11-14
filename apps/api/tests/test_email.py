import json

import httpx
import pytest
from pydantic import SecretStr

from operon.core.config import Settings
from operon.core.email import BrevoEmailSender, EmailMessage, create_email_sender


def _settings(**kw: object) -> Settings:
    return Settings(
        email_backend="brevo",
        brevo_api_key=SecretStr("xkeysib-test"),
        email_from="Operon <ops@example.com>",
        **kw,  # type: ignore[arg-type]
    )


async def test_brevo_sends_over_https_with_the_api_key() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(201, json={"messageId": "<1@brevo>"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        sender = BrevoEmailSender(_settings(), client)
        await sender.send(EmailMessage(to="pat@acme.example", subject="Hi", text="Body"))

    (req,) = seen
    assert str(req.url) == "https://api.brevo.com/v3/smtp/email"
    assert req.headers["api-key"] == "xkeysib-test"
    assert json.loads(req.content) == {
        "sender": {"email": "ops@example.com", "name": "Operon"},
        "to": [{"email": "pat@acme.example"}],
        "subject": "Hi",
        "textContent": "Body",
    }


async def test_brevo_errors_are_raised() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, json={"code": "invalid_parameter"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        sender = BrevoEmailSender(_settings(), client)
        with pytest.raises(httpx.HTTPStatusError):
            await sender.send(EmailMessage(to="pat@acme.example", subject="Hi", text="Body"))


def test_brevo_backend_needs_a_key() -> None:
    with pytest.raises(ValueError, match="OPERON_BREVO_API_KEY"):
        Settings(email_backend="brevo")
    assert isinstance(create_email_sender(_settings()), BrevoEmailSender)
