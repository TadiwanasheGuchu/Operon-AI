"""Integration secrets: encrypted at rest, bound to their connection, never returned by the API."""

import json
from typing import Any
from uuid import UUID

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from operon.core.crypto import SecretBox
from operon.modules.integrations.models import ConnectionCredential


def _context(connection_id: UUID) -> str:
    return f"integration:{connection_id}"


async def store(
    session: AsyncSession,
    box: SecretBox,
    *,
    organisation_id: UUID,
    connection_id: UUID,
    secrets: dict[str, Any],
) -> None:
    encrypted = box.encrypt(json.dumps(secrets), context=_context(connection_id))
    await session.execute(
        insert(ConnectionCredential)
        .values(
            connection_id=connection_id, organisation_id=organisation_id, secret_encrypted=encrypted
        )
        .on_conflict_do_update(
            index_elements=["connection_id"], set_={"secret_encrypted": encrypted}
        )
    )


async def load(session: AsyncSession, box: SecretBox, connection_id: UUID) -> dict[str, Any]:
    row = await session.get(ConnectionCredential, connection_id)
    if row is None:
        return {}
    return dict(json.loads(box.decrypt(row.secret_encrypted, context=_context(connection_id))))
