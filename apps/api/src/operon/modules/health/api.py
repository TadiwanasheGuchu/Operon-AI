from fastapi import APIRouter, Response, status

from operon.core.deps import DatabaseDep, RedisDep, SettingsDep
from operon.modules.health.schemas import LivenessResponse, ReadinessResponse
from operon.modules.health.service import check_dependencies

router = APIRouter(prefix="/health", tags=["health"])


@router.get("/live", response_model=LivenessResponse, summary="Process is running")
async def live(settings: SettingsDep) -> LivenessResponse:
    return LivenessResponse(service=settings.service_name, version=settings.version)


@router.get(
    "/ready",
    response_model=ReadinessResponse,
    summary="Process can serve traffic (database and Redis reachable)",
    responses={503: {"model": ReadinessResponse}},
)
async def ready(
    response: Response, settings: SettingsDep, db: DatabaseDep, redis: RedisDep
) -> ReadinessResponse:
    checks = await check_dependencies(db, redis, settings.health_check_timeout_seconds)
    healthy = all(c.status == "ok" for c in checks)
    if not healthy:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return ReadinessResponse(
        status="ok" if healthy else "unavailable",
        service=settings.service_name,
        version=settings.version,
        checks=checks,
    )
