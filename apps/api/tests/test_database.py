"""Schema and database-role guarantees the rest of the platform relies on."""

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.runtime.migration import MigrationContext
from sqlalchemy import create_engine, text
from sqlalchemy.exc import ProgrammingError

import operon.models  # noqa: F401  — register every table
from operon.core.db import Base
from tests.conftest import TEST_DB_APP_URL, TEST_DB_OWNER_URL, alembic_config

APP_SYNC_URL = TEST_DB_APP_URL.replace("+asyncpg", "+psycopg")


def test_migrations_round_trip() -> None:
    cfg = alembic_config()
    command.downgrade(cfg, "base")
    command.upgrade(cfg, "head")


def test_models_match_migrations() -> None:
    engine = create_engine(TEST_DB_OWNER_URL)
    with engine.connect() as conn:
        diff = compare_metadata(MigrationContext.configure(conn), Base.metadata)
    engine.dispose()
    assert diff == [], f"Models and migrations have drifted: {diff}"


def test_app_role_is_least_privilege() -> None:
    engine = create_engine(APP_SYNC_URL)
    with engine.connect() as conn:
        row = conn.execute(
            text(
                "SELECT rolsuper, rolbypassrls, rolcreaterole, rolcreatedb "
                "FROM pg_roles WHERE rolname = current_user"
            )
        ).one()
        assert tuple(row) == (False, False, False, False)
        with pytest.raises(ProgrammingError):
            conn.execute(text("CREATE TABLE should_not_exist (id int)"))
    engine.dispose()


def test_app_role_can_use_application_tables() -> None:
    engine = create_engine(APP_SYNC_URL)
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO system_events (id, event_type, severity, message, details) "
                "VALUES (gen_random_uuid(), 'test', 'info', 'ok', '{}')"
            )
        )
        conn.execute(text("DELETE FROM system_events WHERE event_type = 'test'"))
    engine.dispose()
