"""Outbound request safety (SSRF protection for user-supplied integration URLs)."""

import asyncio
import ipaddress
import socket
from urllib.parse import urlsplit


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

    `allow_private` is for development/test only (local Odoo, test servers). DNS is resolved
    here and again before each sync; this narrows, but does not eliminate, DNS-rebinding risk.
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
