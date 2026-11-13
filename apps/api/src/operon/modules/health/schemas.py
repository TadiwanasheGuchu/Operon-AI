from typing import Literal

from pydantic import BaseModel

CheckStatus = Literal["ok", "unavailable"]


class DependencyCheck(BaseModel):
    name: str
    status: CheckStatus
    latency_ms: float | None = None


class LivenessResponse(BaseModel):
    status: Literal["ok"] = "ok"
    service: str
    version: str


class ReadinessResponse(BaseModel):
    status: CheckStatus
    service: str
    version: str
    checks: list[DependencyCheck]
