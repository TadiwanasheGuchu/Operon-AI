"""FastAPI dependency providers for shared infrastructure held on ``app.state``."""

from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Depends, Request
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from operon.core.config import Settings
from operon.core.db import Database


def get_settings_dep(request: Request) -> Settings:
    settings: Settings = request.app.state.settings
    return settings


def get_database(request: Request) -> Database:
    db: Database = request.app.state.db
    return db


def get_redis(request: Request) -> "Redis":
    redis: Redis = request.app.state.redis
    return redis


async def get_session(
    db: Annotated[Database, Depends(get_database)],
) -> AsyncIterator[AsyncSession]:
    """One transaction per request: commits when the handler succeeds, rolls back on any error.

    Used with ``scope="function"`` so the commit happens before the response is sent: a failed
    commit becomes an error response instead of a false success. Services never commit.
    """
    async with db.sessionmaker() as session, session.begin():
        yield session


SettingsDep = Annotated[Settings, Depends(get_settings_dep)]
DatabaseDep = Annotated[Database, Depends(get_database)]
RedisDep = Annotated["Redis", Depends(get_redis)]
SessionDep = Annotated[AsyncSession, Depends(get_session, scope="function")]
