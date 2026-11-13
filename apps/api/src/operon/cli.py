"""Operator commands. Usage: ``python -m operon.cli <command> --help``.

seed-demo creates an organisation flagged ``is_demo`` (ADR 0009). It connects as the schema owner
because the application role is deliberately unable to set that flag.
"""

import argparse
import asyncio
import sys
from uuid import UUID

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from operon.access.context import Actor
from operon.core.config import get_settings
from operon.core.db import set_rls_context
from operon.core.ids import uuid7
from operon.modules.audit import service as audit
from operon.modules.identity.models import User
from operon.modules.organisations.models import Membership, Organisation
from operon.modules.permissions import service as roles_service
from operon.modules.permissions.catalogue import SystemRole

DEFAULT_DEMO_NAME = "Harbour & Vale Distribution (demo)"


async def seed_demo(session: AsyncSession, owner_email: str, name: str) -> UUID:
    owner = await session.scalar(select(User).where(User.email == owner_email.strip().lower()))
    if owner is None or owner.email_verified_at is None:
        raise SystemExit(f"No verified account for {owner_email}. Register and confirm it first.")
    org_id = uuid7()
    await set_rls_context(session, user_id=owner.id, organisation_id=org_id)
    session.add(Organisation(id=org_id, name=name, created_by=owner.id))
    await session.flush()
    # The one place the demo flag is set; requires the owner role (column privilege).
    await session.execute(
        text("UPDATE organisations SET is_demo = true WHERE id = :id"), {"id": org_id}
    )
    roles = await roles_service.provision_system_roles(session, org_id)
    session.add(
        Membership(organisation_id=org_id, user_id=owner.id, role_id=roles[SystemRole.OWNER].id)
    )
    await session.flush()
    await audit.record(
        session,
        actor=Actor("system", None, "seed-demo"),
        action="organisation.created",
        meta=None,
        organisation_id=org_id,
        target_type="organisation",
        target_id=org_id,
        details={"name": name, "demo": True, "owner": owner.email},
    )
    return org_id


async def _run_seed(owner_email: str, name: str) -> None:
    settings = get_settings()
    url = settings.migrations_database_url.get_secret_value().replace("+psycopg", "+asyncpg")
    engine = create_async_engine(url)
    try:
        async with async_sessionmaker(engine)() as session, session.begin():
            org_id = await seed_demo(session, owner_email, name)
    finally:
        await engine.dispose()
    print(f"Created demo organisation {name!r} ({org_id}) owned by {owner_email}.")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="operon")
    sub = parser.add_subparsers(dest="command", required=True)
    seed = sub.add_parser("seed-demo", help="Create a demo organisation with labelled sample data")
    seed.add_argument("--owner-email", required=True, help="Existing, verified account to own it")
    seed.add_argument("--name", default=DEFAULT_DEMO_NAME)
    args = parser.parse_args(argv)
    if args.command == "seed-demo":
        asyncio.run(_run_seed(args.owner_email, args.name))


if __name__ == "__main__":
    main(sys.argv[1:])
