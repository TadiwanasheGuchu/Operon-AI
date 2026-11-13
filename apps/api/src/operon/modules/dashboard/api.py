from typing import Annotated

from fastapi import APIRouter, Depends, Query

from operon.access.context import TenantContext
from operon.access.dependencies import AuthDep, require_permission
from operon.core.deps import SessionDep
from operon.modules.dashboard import service
from operon.modules.dashboard.layouts import PRESETS, default_preset
from operon.modules.dashboard.schemas import (
    DashboardSummary,
    LayoutSettingsOut,
    Period,
    PresetOut,
    UpdateLayoutRequest,
)
from operon.modules.permissions.catalogue import Perm

router = APIRouter(prefix="/dashboard", tags=["dashboard"])

DashboardRead = Annotated[TenantContext, Depends(require_permission(Perm.DASHBOARD_READ))]


@router.get(
    "/summary",
    response_model=DashboardSummary,
    summary="Operations overview for the current organisation",
)
async def summary(
    ctx: DashboardRead,
    auth: AuthDep,
    session: SessionDep,
    period: Annotated[Period, Query()] = "7d",
) -> DashboardSummary:
    return await service.build_summary(session, ctx, period, auth.mfa_enabled)


async def _settings(session: SessionDep, ctx: TenantContext) -> LayoutSettingsOut:
    return LayoutSettingsOut(
        current=await service.get_layout(session, ctx),
        default_preset=default_preset(ctx.role_key),
        presets=[
            PresetOut(key=p.key, name=p.name, description=p.description) for p in PRESETS.values()
        ],
    )


@router.get("/layout", response_model=LayoutSettingsOut)
async def get_layout(ctx: DashboardRead, session: SessionDep) -> LayoutSettingsOut:
    return await _settings(session, ctx)


@router.put(
    "/layout",
    response_model=LayoutSettingsOut,
    summary="Choose an overview layout (null resets to your role's default)",
)
async def put_layout(
    body: UpdateLayoutRequest, ctx: DashboardRead, session: SessionDep
) -> LayoutSettingsOut:
    await service.set_layout(session, ctx, body.preset)
    return await _settings(session, ctx)
