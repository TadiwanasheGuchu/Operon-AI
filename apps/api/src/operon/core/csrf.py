"""CSRF protection: double-submit cookie (ADR 0001).

Every response ensures a random, non-HttpOnly ``operon_csrf`` cookie exists. State-changing
requests must echo it in the ``X-CSRF-Token`` header. A cross-site attacker can make the browser
send cookies but cannot read them, so cannot produce the header. Combined with SameSite=Lax.
"""

import json
import secrets
from http.cookies import SimpleCookie

from starlette.types import ASGIApp, Message, Receive, Scope, Send

from operon.core.config import Settings
from operon.core.request_context import get_request_id
from operon.core.security import tokens_equal

UNSAFE_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})
HEADER = b"x-csrf-token"
# Machine-to-machine endpoints authenticate by signature, not cookies (Phase 3 webhooks).
EXEMPT_PREFIXES = ("/api/v1/webhooks/",)


class CsrfMiddleware:
    def __init__(self, app: ASGIApp, settings: Settings) -> None:
        self.app = app
        self.cookie_name = settings.csrf_cookie_name
        self.secure = settings.secure_cookies

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers = dict(scope["headers"])
        cookies = SimpleCookie()
        cookies.load(headers.get(b"cookie", b"").decode("latin-1"))
        cookie_token = cookies[self.cookie_name].value if self.cookie_name in cookies else None

        path: str = scope["path"]
        if scope["method"] in UNSAFE_METHODS and not path.startswith(EXEMPT_PREFIXES):
            header_token = headers.get(HEADER, b"").decode("latin-1")
            if not cookie_token or not header_token or not tokens_equal(cookie_token, header_token):
                await self._reject(send)
                return

        new_token = None if cookie_token else secrets.token_urlsafe(32)

        async def send_wrapper(message: Message) -> None:
            if new_token and message["type"] == "http.response.start":
                attrs = f"{self.cookie_name}={new_token}; Path=/; SameSite=Lax"
                if self.secure:
                    attrs += "; Secure"
                message.setdefault("headers", []).append((b"set-cookie", attrs.encode()))
            await send(message)

        await self.app(scope, receive, send_wrapper)

    async def _reject(self, send: Send) -> None:
        body = json.dumps(
            {
                "error": {
                    "code": "csrf_failed",
                    "message": "The request could not be verified. Reload the page and try again.",
                    "details": {},
                    "request_id": get_request_id(),
                }
            }
        ).encode()
        await send(
            {
                "type": "http.response.start",
                "status": 403,
                "headers": [(b"content-type", b"application/json")],
            }
        )
        await send({"type": "http.response.body", "body": body})
