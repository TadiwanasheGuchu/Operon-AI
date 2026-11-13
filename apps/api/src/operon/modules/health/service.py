"""Readiness checks for the API's hard dependencies."""

import asyncio
import time
from collections.abc import Awaitable, Callable

from redis.asyncio import Redis
from sqlalchemy import text

from operon.core.db import Database
from operon.core.logging import get_logger
from operon.modules.health.schemas import DependencyCheck

log = get_logger(__name__)


async def _timed(
    name: str, probe: Callable[[], Awaitable[object]], timeout_seconds: float
) -> DependencyCheck:
    started = time.perf_counter()
    try:
        await asyncio.wait_for(probe(), timeout=timeout_seconds)
    except Exception as exc:
        # Detail goes to logs only; the API response never exposes infrastructure errors.
        log.warning("dependency_unavailable", dependency=name, error_type=type(exc).__name__)
        return DependencyCheck(name=name, status="unavailable")
    return DependencyCheck(
        name=name, status="ok", latency_ms=round((time.perf_counter() - started) * 1000, 1)
    )


async def check_dependencies(
    db: Database, redis: "Redis", timeout_seconds: float
) -> list[DependencyCheck]:
    async def db_probe() -> None:
        async with db.engine.connect() as conn:
            await conn.execute(text("SELECT 1"))

    async def redis_probe() -> None:
        await redis.ping()

    return list(
        await asyncio.gather(
            _timed("database", db_probe, timeout_seconds),
            _timed("redis", redis_probe, timeout_seconds),
        )
    )
