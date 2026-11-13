from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, status

from operon.access.context import TenantContext
from operon.access.dependencies import (
    AuthDep,
    IdentityDep,
    MetaDep,
    require_permission,
)
from operon.core.deps import SessionDep, SettingsDep
from operon.modules.identity.schemas import OrganisationSummary
from operon.modules.organisations import schemas as s
from operon.modules.organisations import service
from operon.modules.permissions.catalogue import Perm

router = APIRouter(tags=["organisations"])


OrgRead = Annotated[TenantContext, Depends(require_permission(Perm.ORGANISATION_READ))]
OrgManage = Annotated[TenantContext, Depends(require_permission(Perm.ORGANISATION_MANAGE))]
MembersRead = Annotated[TenantContext, Depends(require_permission(Perm.MEMBERS_READ))]
MembersInvite = Annotated[TenantContext, Depends(require_permission(Perm.MEMBERS_INVITE))]
MembersManage = Annotated[TenantContext, Depends(require_permission(Perm.MEMBERS_MANAGE))]


def _org_out(org: object) -> s.OrganisationOut:
    return s.OrganisationOut.model_validate(org, from_attributes=True)


@router.get(
    "/organisations",
    response_model=list[OrganisationSummary],
    summary="Organisations you belong to",
)
async def my_organisations(auth: AuthDep, session: SessionDep) -> list[OrganisationSummary]:
    return [
        OrganisationSummary(**o.__dict__)
        for o in await service.list_my_organisations(session, auth.user_id)
    ]


@router.post(
    "/organisations", response_model=s.OrganisationOut, status_code=status.HTTP_201_CREATED
)
async def create_organisation(
    body: s.CreateOrganisationRequest, auth: AuthDep, identity: IdentityDep, meta: MetaDep
) -> s.OrganisationOut:
    user = await identity.get_user(auth.user_id)
    return _org_out(
        await service.create_organisation(identity.s, name=body.name, owner=user, meta=meta)
    )


@router.get("/organisations/current", response_model=s.CurrentOrganisationOut)
async def current_organisation(ctx: OrgRead, session: SessionDep) -> s.CurrentOrganisationOut:
    org = await service.get_current(session, ctx)
    return s.CurrentOrganisationOut(
        **_org_out(org).model_dump(), role_key=ctx.role_key, permissions=sorted(ctx.permissions)
    )


@router.patch("/organisations/current", response_model=s.OrganisationOut)
async def update_organisation(
    body: s.UpdateOrganisationRequest,
    ctx: OrgManage,
    auth: AuthDep,
    session: SessionDep,
    meta: MetaDep,
) -> s.OrganisationOut:
    return _org_out(
        await service.update_organisation(
            session,
            ctx,
            name=body.name,
            mfa_required=body.mfa_required,
            actor_mfa_enabled=auth.mfa_enabled,
            meta=meta,
        )
    )


@router.get("/members", response_model=list[s.MemberOut], tags=["members"])
async def list_members(ctx: MembersRead, session: SessionDep) -> list[s.MemberOut]:
    return [
        s.MemberOut(**m.__dict__, is_you=m.user_id == ctx.user_id)
        for m in await service.list_members(session, ctx)
    ]


@router.patch("/members/{member_id}", response_model=s.MemberOut, tags=["members"])
async def change_role(
    member_id: UUID,
    body: s.ChangeRoleRequest,
    ctx: MembersManage,
    session: SessionDep,
    meta: MetaDep,
) -> s.MemberOut:
    m = await service.change_member_role(session, ctx, member_id, body.role_key, meta)
    return s.MemberOut(**m.__dict__, is_you=False)


@router.delete("/members/{member_id}", status_code=status.HTTP_204_NO_CONTENT, tags=["members"])
async def remove_member(
    member_id: UUID, ctx: MembersManage, session: SessionDep, meta: MetaDep
) -> None:
    await service.remove_member(session, ctx, member_id, meta)


@router.get("/invitations", response_model=list[s.InvitationOut], tags=["invitations"])
async def list_invitations(ctx: MembersRead, session: SessionDep) -> list[s.InvitationOut]:
    return [s.InvitationOut(**i.__dict__) for i in await service.list_invitations(session, ctx)]


@router.post(
    "/invitations",
    response_model=s.InvitationOut,
    status_code=status.HTTP_201_CREATED,
    tags=["invitations"],
)
async def create_invitation(
    body: s.CreateInvitationRequest,
    ctx: MembersInvite,
    auth: AuthDep,
    session: SessionDep,
    settings: SettingsDep,
    request: Request,
    meta: MetaDep,
) -> s.InvitationOut:
    i = await service.create_invitation(
        session,
        ctx,
        email=body.email,
        role_key=body.role_key,
        inviter_name=auth.full_name,
        settings=settings,
        mailer=request.app.state.mailer,
        meta=meta,
    )
    return s.InvitationOut(**i.__dict__)


@router.delete(
    "/invitations/{invitation_id}", status_code=status.HTTP_204_NO_CONTENT, tags=["invitations"]
)
async def revoke_invitation(
    invitation_id: UUID, ctx: MembersInvite, session: SessionDep, meta: MetaDep
) -> None:
    await service.revoke_invitation(session, ctx, invitation_id, meta)


@router.get(
    "/invitations/lookup",
    response_model=s.InvitationLookupOut,
    tags=["invitations"],
    summary="Describe an invitation from its link (no sign-in required)",
)
async def lookup_invitation(
    token: Annotated[str, Query(min_length=20, max_length=200)], session: SessionDep
) -> s.InvitationLookupOut:
    found = await service.lookup_invitation(session, token)
    return s.InvitationLookupOut(
        organisation_name=found.organisation_name,
        email=found.invitation.email,
        role_name=found.role_name,
        invited_by=found.inviter_name,
        expires_at=found.invitation.expires_at,
        status=found.status,
    )


@router.post("/invitations/accept", response_model=s.AcceptInvitationResponse, tags=["invitations"])
async def accept_invitation(
    body: s.AcceptInvitationRequest, auth: AuthDep, identity: IdentityDep, meta: MetaDep
) -> s.AcceptInvitationResponse:
    user = await identity.get_user(auth.user_id)
    org_id = await service.accept_invitation(identity.s, token=body.token, user=user, meta=meta)
    return s.AcceptInvitationResponse(organisation_id=org_id)
