import json

import structlog

from operon.core.ids import uuid7
from operon.core.logging import configure_logging, get_logger


def test_uuid7_version_variant_and_ordering() -> None:
    ids = [uuid7() for _ in range(200)]
    assert all(u.version == 7 for u in ids)
    assert all(u.variant == "specified in RFC 4122" for u in ids)
    # Millisecond prefix is monotonic (within-ms order is random by design).
    prefixes = [u.int >> 80 for u in ids]
    assert prefixes == sorted(prefixes)
    assert len(set(ids)) == len(ids)


def test_sensitive_fields_are_redacted(capsys) -> None:  # type: ignore[no-untyped-def]
    structlog.reset_defaults()
    configure_logging("INFO", json=True)
    get_logger("t").info("login", password="hunter2", api_key="k", user="ana")
    line = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert line["password"] == "[REDACTED]"
    assert line["api_key"] == "[REDACTED]"
    assert line["user"] == "ana"
