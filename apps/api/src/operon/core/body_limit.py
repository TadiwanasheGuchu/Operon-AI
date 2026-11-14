"""Request body size limits (security review, Phase 7).

JSON endpoints accept at most 1 MB; CSV uploads up to the configured upload size plus multipart
overhead. Checked against Content-Length up front and counted while streaming, so a missing or
false Content-Length can't get around it.
"""

import json

from starlette.types import ASGIApp, Message, Receive, Scope, Send

from operon.core.config import Settings

DEFAULT_MAX = 1024 * 1024
MULTIPART_OVERHEAD = 64 * 1024


class _TooLargeError(Exception):
    pass


class BodyLimitMiddleware:
    def __init__(self, app: ASGIApp, settings: Settings) -> None:
        self.app = app
        self.upload_max = settings.max_upload_bytes + MULTIPART_OVERHEAD

    def _limit(self, path: str) -> int:
        return self.upload_max if path.endswith("/uploads") else DEFAULT_MAX

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope["method"] in ("GET", "HEAD", "OPTIONS"):
            await self.app(scope, receive, send)
            return
        limit = self._limit(scope["path"])
        declared = dict(scope["headers"]).get(b"content-length")
        if declared is not None and declared.isdigit() and int(declared) > limit:
            await self._reject(send, limit)
            return
        received = 0
        started = False

        async def counting_receive() -> Message:
            nonlocal received
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > limit:
                    raise _TooLargeError
            return message

        async def tracking_send(message: Message) -> None:
            nonlocal started
            if message["type"] == "http.response.start":
                started = True
            await send(message)

        try:
            await self.app(scope, counting_receive, tracking_send)
        except _TooLargeError:
            if not started:
                await self._reject(send, limit)

    @staticmethod
    async def _reject(send: Send, limit: int) -> None:
        body = json.dumps(
            {
                "error": {
                    "code": "payload_too_large",
                    "message": f"The request is larger than the {limit // 1024} KB allowed.",
                    "details": {},
                }
            }
        ).encode()
        await send(
            {
                "type": "http.response.start",
                "status": 413,
                "headers": [(b"content-type", b"application/json")],
            }
        )
        await send({"type": "http.response.body", "body": body})
