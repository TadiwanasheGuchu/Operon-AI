from typing import Annotated

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from operon.access.context import TenantContext
from operon.access.dependencies import MetaDep, require_permission
from operon.core import usage_limits as usage
from operon.core.deps import SessionDep
from operon.modules.governance import service
from operon.modules.governance.models import RETENTION_BOUNDS
from operon.modules.permissions.catalogue import Perm

router = APIRouter(tags=["governance"])

OrgRead = Annotated[TenantContext, Depends(require_permission(Perm.ORGANISATION_READ))]
OrgManage = Annotated[TenantContext, Depends(require_permission(Perm.ORGANISATION_MANAGE))]


class RetentionOut(BaseModel):
    audit_days: int
    conversation_days: int
    run_log_days: int
    sync_job_days: int
    bounds: dict[str, tuple[int, int]]


def _out(p: object) -> RetentionOut:
    return RetentionOut(
        **{k: getattr(p, k) for k in RETENTION_BOUNDS}, bounds=dict(RETENTION_BOUNDS)
    )


@router.get("/organisations/current/retention", response_model=RetentionOut)
async def get_retention(ctx: OrgRead, session: SessionDep) -> RetentionOut:
    return _out(await service.policy(session, ctx.organisation_id))


@router.put("/organisations/current/retention", response_model=RetentionOut)
async def put_retention(
    body: service.RetentionUpdate, ctx: OrgManage, session: SessionDep, meta: MetaDep
) -> RetentionOut:
    return _out(await service.update_policy(session, ctx, body, meta))


@router.post("/organisations/current/export", summary="Download the organisation's data (ZIP)")
async def export(
    ctx: OrgManage, session: SessionDep, request: Request, meta: MetaDep
) -> StreamingResponse:
    await usage.hit(request, usage.EXPORTS_PER_ORG, ctx.organisation_id)
    f = await service.export_organisation(session, ctx, meta)
    return StreamingResponse(
        service.iter_file(f.path),
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{f.filename}"'},
    )
