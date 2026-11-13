"""Permission catalogue and system roles — defined in code, synchronised by migrations.

Adding a permission: add it here, then add a migration that inserts it into `permissions` and
grants it to the right system roles (tests fail if code and database disagree).
"""

from enum import StrEnum


class Perm(StrEnum):
    ORGANISATION_READ = "organisation.read"
    ORGANISATION_MANAGE = "organisation.manage"
    MEMBERS_READ = "members.read"
    MEMBERS_INVITE = "members.invite"
    MEMBERS_MANAGE = "members.manage"
    ROLES_READ = "roles.read"
    AUDIT_READ = "audit.read"
    DASHBOARD_READ = "dashboard.read"
    INTEGRATIONS_READ = "integrations.read"
    INTEGRATIONS_MANAGE = "integrations.manage"
    INSIGHTS_READ = "insights.read"
    INSIGHTS_MANAGE = "insights.manage"
    INCIDENTS_READ = "incidents.read"
    INCIDENTS_MANAGE = "incidents.manage"
    WORKFLOWS_READ = "workflows.read"
    WORKFLOWS_REQUEST = "workflows.request"
    WORKFLOWS_MANAGE = "workflows.manage"
    APPROVALS_DECIDE = "approvals.decide"


PERMISSION_DESCRIPTIONS: dict[Perm, str] = {
    Perm.ORGANISATION_READ: "View organisation details",
    Perm.ORGANISATION_MANAGE: "Change organisation settings and security policy",
    Perm.MEMBERS_READ: "View members and pending invitations",
    Perm.MEMBERS_INVITE: "Invite people to the organisation",
    Perm.MEMBERS_MANAGE: "Change members' roles and remove members",
    Perm.ROLES_READ: "View roles and their permissions",
    Perm.AUDIT_READ: "View the organisation audit log",
    Perm.DASHBOARD_READ: "View the operations overview",
    Perm.INTEGRATIONS_READ: "View connected systems and their sync status",
    Perm.INTEGRATIONS_MANAGE: "Connect, configure and disconnect systems; import data",
    Perm.INSIGHTS_READ: "View insights, their evidence and detector settings",
    Perm.INSIGHTS_MANAGE: "Act on insights, assign owners, run detection and tune detectors",
    Perm.INCIDENTS_READ: "View incidents and their timelines",
    Perm.INCIDENTS_MANAGE: "Open, assign, update and resolve incidents",
    Perm.WORKFLOWS_READ: "View purchase requests and workflow executions",
    Perm.WORKFLOWS_REQUEST: "Submit purchase requests for approval",
    Perm.WORKFLOWS_MANAGE: "Configure workflows and approval policy; retry or cancel executions",
    Perm.APPROVALS_DECIDE: "Approve or reject requests at stages assigned to your role",
}


class SystemRole(StrEnum):
    OWNER = "owner"
    ADMINISTRATOR = "administrator"
    OPERATIONS_MANAGER = "operations_manager"
    APPROVER = "approver"
    ANALYST = "analyst"
    VIEWER = "viewer"


ALL = frozenset(Perm)

SYSTEM_ROLES: dict[SystemRole, tuple[str, str, frozenset[Perm]]] = {
    SystemRole.OWNER: ("Owner", "Full control, including ownership and security policy.", ALL),
    SystemRole.ADMINISTRATOR: (
        "Administrator",
        "Manages members and settings. Cannot grant or change ownership.",
        ALL,
    ),
    SystemRole.OPERATIONS_MANAGER: (
        "Operations manager",
        "Runs day-to-day operations and reviews activity.",
        frozenset(
            {
                Perm.ORGANISATION_READ,
                Perm.MEMBERS_READ,
                Perm.ROLES_READ,
                Perm.AUDIT_READ,
                Perm.DASHBOARD_READ,
                Perm.INTEGRATIONS_READ,
                Perm.INSIGHTS_READ,
                Perm.INSIGHTS_MANAGE,
                Perm.INCIDENTS_READ,
                Perm.INCIDENTS_MANAGE,
                Perm.WORKFLOWS_READ,
                Perm.WORKFLOWS_REQUEST,
                Perm.APPROVALS_DECIDE,
            }
        ),
    ),
    SystemRole.APPROVER: (
        "Approver",
        "Decides on requests that need approval.",
        frozenset(
            {
                Perm.ORGANISATION_READ,
                Perm.MEMBERS_READ,
                Perm.DASHBOARD_READ,
                Perm.INSIGHTS_READ,
                Perm.INCIDENTS_READ,
                Perm.WORKFLOWS_READ,
                Perm.APPROVALS_DECIDE,
            }
        ),
    ),
    SystemRole.ANALYST: (
        "Analyst",
        "Investigates performance and reviews activity.",
        frozenset(
            {
                Perm.ORGANISATION_READ,
                Perm.MEMBERS_READ,
                Perm.AUDIT_READ,
                Perm.DASHBOARD_READ,
                Perm.INTEGRATIONS_READ,
                Perm.INSIGHTS_READ,
                Perm.INCIDENTS_READ,
                Perm.WORKFLOWS_READ,
            }
        ),
    ),
    SystemRole.VIEWER: (
        "Viewer",
        "Read-only access to the operations overview.",
        frozenset(
            {Perm.ORGANISATION_READ, Perm.DASHBOARD_READ, Perm.INSIGHTS_READ, Perm.INCIDENTS_READ}
        ),
    ),
}

# Rank used to stop people granting roles above their own (lower = more privileged).
ROLE_RANK: dict[str, int] = {r.value: i for i, r in enumerate(SystemRole)}
