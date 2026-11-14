"""Outbound request safety (SSRF protection for user-supplied integration URLs)."""

import asyncio
import ipaddress
import os
import socket
import ssl
from collections.abc import Iterable
from typing import Any
from urllib.parse import urlsplit

import certifi
import httpcore
import httpx


class UnsafeUrlError(ValueError):
    pass


def _is_private(address: str) -> bool:
    ip = ipaddress.ip_address(address)
    return (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified
    )


async def validate_outbound_url(url: str, *, allow_private: bool) -> str:
    """Require https and a public destination. Returns the normalised base URL.

    `allow_private` is for development/test only (local Odoo, test servers). This is the early,
    user-facing check; `GuardedTransport` repeats it at connect time, which closes the
    DNS-rebinding gap.
    """
    parts = urlsplit(url.strip())
    if parts.scheme not in ("https", "http") or not parts.hostname:
        raise UnsafeUrlError("Enter a full address, for example https://yourcompany.odoo.com.")
    if parts.username or parts.password:
        raise UnsafeUrlError("Don't include credentials in the address.")
    if parts.scheme != "https" and not allow_private:
        raise UnsafeUrlError("The address must use https.")
    if not allow_private:
        try:
            infos = await asyncio.get_running_loop().getaddrinfo(
                parts.hostname, parts.port or 443, type=socket.SOCK_STREAM
            )
        except socket.gaierror as exc:
            raise UnsafeUrlError("That address could not be found.") from exc
        if any(_is_private(str(info[4][0])) for info in infos):
            raise UnsafeUrlError("That address points to a private network, which isn't allowed.")
    netloc = parts.hostname + (f":{parts.port}" if parts.port else "")
    return f"{parts.scheme}://{netloc}{parts.path.rstrip('/')}"


# --- connect-time guard (closes the DNS-rebinding gap) ---------------------------------------


class _GuardedBackend(httpcore.AsyncNetworkBackend):
    """Resolves, checks and connects in one step, so the address checked is the address used.

    TLS still verifies the certificate against the original hostname (httpcore passes the
    request's host as the server name), so connecting by IP doesn't weaken TLS.
    """

    def __init__(self) -> None:
        self._inner = httpcore.AnyIOBackend()

    async def connect_tcp(
        self,
        host: str,
        port: int,
        timeout: float | None = None,  # noqa: ASYNC109 — httpcore's interface
        local_address: str | None = None,
        socket_options: Iterable[Any] | None = None,
    ) -> httpcore.AsyncNetworkStream:
        try:
            infos = await asyncio.get_running_loop().getaddrinfo(
                host, port, type=socket.SOCK_STREAM
            )
        except socket.gaierror as exc:
            raise httpcore.ConnectError(f"Could not resolve {host}") from exc
        addresses = [str(i[4][0]) for i in infos]
        if not addresses or any(_is_private(a) for a in addresses):
            raise httpcore.ConnectError(f"Refusing to connect to a private address for {host}")
        return await self._inner.connect_tcp(
            addresses[0],
            port,
            timeout=timeout,
            local_address=local_address,
            socket_options=socket_options,
        )

    async def connect_unix_socket(
        self,
        path: str,
        timeout: float | None = None,  # noqa: ASYNC109 — httpcore's interface
        socket_options: Iterable[Any] | None = None,
    ) -> httpcore.AsyncNetworkStream:
        raise httpcore.ConnectError("Unix sockets are not allowed for outbound integrations.")

    async def sleep(self, seconds: float) -> None:
        await self._inner.sleep(seconds)


class GuardedTransport(httpx.AsyncHTTPTransport):
    """An httpx transport that only ever connects to public addresses."""

    def __init__(self) -> None:
        super().__init__(trust_env=False)
        ssl_context = ssl.create_default_context(cafile=certifi.where())
        # httpx has no public hook for the network backend; the pool is replaced wholesale.
        self._pool = httpcore.AsyncConnectionPool(
            ssl_context=ssl_context, network_backend=_GuardedBackend(), max_connections=20
        )


def outbound_proxy_configured() -> bool:
    """With an egress proxy, the proxy makes the connection and must enforce this itself."""
    return any(os.environ.get(k) for k in ("HTTPS_PROXY", "https_proxy", "ALL_PROXY", "all_proxy"))
