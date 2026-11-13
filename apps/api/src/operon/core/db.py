"""Database engine, session factory and declarative base."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, MetaData, func, text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from operon.core.config import Settings
from operon.core.ids import uuid7

# Deterministic constraint names keep Alembic autogenerate diffs stable.
NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


class IdMixin:
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid7)


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class Database:
    """Owns the async engine for the lifetime of the application."""

    def __init__(self, settings: Settings) -> None:
        self.engine: AsyncEngine = create_async_engine(
            str(settings.database_url),
            pool_size=settings.database_pool_size,
            pool_pre_ping=True,
        )
        self.sessionmaker = async_sessionmaker(self.engine, expire_on_commit=False)

    async def dispose(self) -> None:
        await self.engine.dispose()


async def set_rls_context(
    session: AsyncSession, *, user_id: UUID | None = None, organisation_id: UUID | None = None
) -> None:
    """Set row-level-security context for the current transaction (SET LOCAL semantics).

    Must be called inside a transaction; the values vanish at commit or rollback, so pooled
    connections never carry one request's tenant into another.
    """
    if user_id is not None:
        await session.execute(
            text("SELECT set_config('app.current_user_id', :v, true)"), {"v": str(user_id)}
        )
    if organisation_id is not None:
        await session.execute(
            text("SELECT set_config('app.current_org_id', :v, true)"), {"v": str(organisation_id)}
        )
