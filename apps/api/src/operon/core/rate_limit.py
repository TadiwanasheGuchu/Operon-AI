"""Fixed-window rate limiting in Redis.

Fails closed: if Redis is unavailable, rate-limited operations (authentication) are refused
rather than left unprotected against brute force.
"""

from dataclasses import dataclass

from redis.asyncio import Redis
from redis.exceptions import RedisError

from operon.core.errors import ApiError
from operon.core.logging import get_logger

log = get_logger(__name__)


@dataclass(frozen=True)
class Limit:
    name: str
    max_hits: int
    window_seconds: int
    message: str = "Too many attempts. Try again later."


class RateLimiter:
    def __init__(self, redis: "Redis") -> None:
        self._redis = redis

    async def hit(self, limit: Limit, subject: str) -> None:
        key = f"ratelimit:{limit.name}:{subject}"
        try:
            async with self._redis.pipeline(transaction=True) as pipe:
                pipe.incr(key)
                pipe.expire(key, limit.window_seconds, nx=True)
                pipe.ttl(key)
                count, _, ttl = await pipe.execute()
        except RedisError as exc:
            log.error("rate_limiter_unavailable", limit=limit.name, error_type=type(exc).__name__)
            raise ApiError(
                503, "temporarily_unavailable", "This action is temporarily unavailable."
            ) from exc
        if int(count) > limit.max_hits:
            raise ApiError(
                429,
                "rate_limited",
                limit.message,
                {"retry_after_seconds": max(int(ttl), 1)},
            )

    async def reset(self, limit: Limit, subject: str) -> None:
        try:
            await self._redis.delete(f"ratelimit:{limit.name}:{subject}")
        except RedisError:
            log.warning("rate_limiter_reset_failed", limit=limit.name)
