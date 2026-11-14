"""Connect-time SSRF guard: the address checked is the address connected to."""

import socket
from typing import Any

import httpcore
import httpx
import pytest

from operon.core import net


async def test_guard_refuses_private_addresses_at_connect_time(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []

    async def rebinding(self: Any, host: str, port: int, **kw: Any) -> list[Any]:
        # First lookup (the early check) would be public; at connect time it's internal.
        calls.append(host)
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("169.254.169.254", port))]

    monkeypatch.setattr("asyncio.base_events.BaseEventLoop.getaddrinfo", rebinding)
    async with httpx.AsyncClient(transport=net.GuardedTransport()) as client:
        with pytest.raises(httpx.ConnectError, match="private address"):
            await client.get("https://odoo.example.com/web")
    assert calls == ["odoo.example.com"]


async def test_guard_connects_to_the_checked_public_address(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def public(self: Any, host: str, port: int, **kw: Any) -> list[Any]:
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.215.14", port))]

    connected: list[str] = []

    async def fake_connect(self: Any, host: str, port: int, **kw: Any) -> Any:
        connected.append(host)
        raise httpcore.ConnectError("stop here")

    monkeypatch.setattr("asyncio.base_events.BaseEventLoop.getaddrinfo", public)
    monkeypatch.setattr(httpcore.AnyIOBackend, "connect_tcp", fake_connect)
    async with httpx.AsyncClient(transport=net.GuardedTransport()) as client:
        with pytest.raises(httpx.ConnectError):
            await client.get("https://odoo.example.com/web")
    assert connected == ["93.184.215.14"]
