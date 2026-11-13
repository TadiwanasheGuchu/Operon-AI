"""Identity, organisations, roles and permissions, audit log, row-level security.

Revision ID: 0002
Revises: 0001
Create Date: 2026-11-13 10:07:31.922704
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "audit_logs",
        sa.Column("organisation_id", sa.Uuid(), nullable=True),
        sa.Column(
            "occurred_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("actor_type", sa.String(length=20), nullable=False),
        sa.Column("actor_user_id", sa.Uuid(), nullable=True),
        sa.Column("actor_label", sa.String(length=320), nullable=False),
        sa.Column("action", sa.String(length=100), nullable=False),
        sa.Column("target_type", sa.String(length=60), nullable=True),
        sa.Column("target_id", sa.String(length=100), nullable=True),
        sa.Column("outcome", sa.String(length=20), nullable=False),
        sa.Column("details", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("request_id", sa.String(length=128), nullable=True),
        sa.Column("ip_address", postgresql.INET(), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.CheckConstraint(
            "actor_type IN ('user', 'system', 'agent')", name=op.f("ck_audit_logs_actor_type_valid")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_audit_logs")),
    )
    op.create_index(
        "ix_audit_logs_actor", "audit_logs", ["actor_user_id", "occurred_at"], unique=False
    )
    op.create_index(
        "ix_audit_logs_org_occurred", "audit_logs", ["organisation_id", "occurred_at"], unique=False
    )
    op.create_table(
        "permissions",
        sa.Column("key", sa.String(length=100), nullable=False),
        sa.Column("description", sa.String(length=300), nullable=False),
        sa.PrimaryKeyConstraint("key", name=op.f("pk_permissions")),
    )
    op.create_table(
        "users",
        sa.Column("email", postgresql.CITEXT(), nullable=False),
        sa.Column("full_name", sa.String(length=200), nullable=False),
        sa.Column("email_verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_users")),
        sa.UniqueConstraint("email", name=op.f("uq_users_email")),
    )
    op.create_table(
        "mfa_factors",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("secret_encrypted", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_used_step", sa.Integer(), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_mfa_factors_user_id_users"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_mfa_factors")),
        sa.UniqueConstraint("user_id", name=op.f("uq_mfa_factors_user_id")),
    )
    op.create_table(
        "organisations",
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("mfa_required", sa.Boolean(), nullable=False),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["users.id"],
            name=op.f("fk_organisations_created_by_users"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_organisations")),
    )
    op.create_table(
        "recovery_codes",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("code_hash", sa.String(length=64), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_recovery_codes_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_recovery_codes")),
    )
    op.create_index(op.f("ix_recovery_codes_user_id"), "recovery_codes", ["user_id"], unique=False)
    op.create_table(
        "user_action_tokens",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("purpose", sa.String(length=30), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.CheckConstraint(
            "purpose IN ('verify_email', 'reset_password')",
            name=op.f("ck_user_action_tokens_purpose_valid"),
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_user_action_tokens_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_user_action_tokens")),
        sa.UniqueConstraint("token_hash", name=op.f("uq_user_action_tokens_token_hash")),
    )
    op.create_index(
        "ix_user_action_tokens_user_purpose",
        "user_action_tokens",
        ["user_id", "purpose"],
        unique=False,
    )
    op.create_table(
        "user_credentials",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("password_hash", sa.Text(), nullable=False),
        sa.Column("password_changed_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_user_credentials_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("user_id", name=op.f("pk_user_credentials")),
    )
    op.create_table(
        "user_sessions",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ip_address", postgresql.INET(), nullable=True),
        sa.Column("user_agent", sa.String(length=400), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_user_sessions_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_user_sessions")),
        sa.UniqueConstraint("token_hash", name=op.f("uq_user_sessions_token_hash")),
    )
    op.create_index(
        "ix_user_sessions_user_id_active", "user_sessions", ["user_id", "revoked_at"], unique=False
    )
    op.create_table(
        "roles",
        sa.Column("organisation_id", sa.Uuid(), nullable=False),
        sa.Column("key", sa.String(length=60), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("description", sa.String(length=300), nullable=False),
        sa.Column("is_system", sa.Boolean(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["organisation_id"],
            ["organisations.id"],
            name=op.f("fk_roles_organisation_id_organisations"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_roles")),
        sa.UniqueConstraint("organisation_id", "id", name="uq_roles_organisation_id_id"),
        sa.UniqueConstraint("organisation_id", "key", name=op.f("uq_roles_organisation_id_key")),
    )
    op.create_table(
        "invitations",
        sa.Column("organisation_id", sa.Uuid(), nullable=False),
        sa.Column("email", postgresql.CITEXT(), nullable=False),
        sa.Column("role_id", sa.Uuid(), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("invited_by", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["invited_by"],
            ["users.id"],
            name=op.f("fk_invitations_invited_by_users"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["organisation_id", "role_id"],
            ["roles.organisation_id", "roles.id"],
            name="fk_invitations_role_same_org",
        ),
        sa.ForeignKeyConstraint(
            ["organisation_id"],
            ["organisations.id"],
            name=op.f("fk_invitations_organisation_id_organisations"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_invitations")),
        sa.UniqueConstraint("token_hash", name=op.f("uq_invitations_token_hash")),
    )
    op.create_index(
        op.f("ix_invitations_organisation_id"), "invitations", ["organisation_id"], unique=False
    )
    op.create_index(
        "uq_invitations_open_per_email",
        "invitations",
        ["organisation_id", "email"],
        unique=True,
        postgresql_where=sa.text("accepted_at IS NULL AND revoked_at IS NULL"),
    )
    op.create_table(
        "organisation_members",
        sa.Column("organisation_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("role_id", sa.Uuid(), nullable=False),
        sa.Column("invited_by", sa.Uuid(), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["invited_by"],
            ["users.id"],
            name=op.f("fk_organisation_members_invited_by_users"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["organisation_id", "role_id"],
            ["roles.organisation_id", "roles.id"],
            name="fk_organisation_members_role_same_org",
        ),
        sa.ForeignKeyConstraint(
            ["organisation_id"],
            ["organisations.id"],
            name=op.f("fk_organisation_members_organisation_id_organisations"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_organisation_members_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_organisation_members")),
        sa.UniqueConstraint(
            "organisation_id",
            "user_id",
            name=op.f("uq_organisation_members_organisation_id_user_id"),
        ),
    )
    op.create_index(
        "ix_organisation_members_user_id", "organisation_members", ["user_id"], unique=False
    )
    op.create_table(
        "role_permissions",
        sa.Column("organisation_id", sa.Uuid(), nullable=False),
        sa.Column("role_id", sa.Uuid(), nullable=False),
        sa.Column("permission_key", sa.String(length=100), nullable=False),
        sa.ForeignKeyConstraint(
            ["organisation_id", "role_id"],
            ["roles.organisation_id", "roles.id"],
            name="fk_role_permissions_role_same_org",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["organisation_id"],
            ["organisations.id"],
            name=op.f("fk_role_permissions_organisation_id_organisations"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["permission_key"],
            ["permissions.key"],
            name=op.f("fk_role_permissions_permission_key_permissions"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("role_id", "permission_key", name=op.f("pk_role_permissions")),
    )
    op.create_index("ix_role_permissions_organisation_id", "role_permissions", ["organisation_id"])

    _seed_permissions()
    _row_level_security()
    _grants()


# Snapshot of operon.modules.permissions.catalogue at this revision. Migrations never import
# application code, so later catalogue changes need their own migration.
PERMISSIONS = [
    ("organisation.read", "View organisation details"),
    ("organisation.manage", "Change organisation settings and security policy"),
    ("members.read", "View members and pending invitations"),
    ("members.invite", "Invite people to the organisation"),
    ("members.manage", "Change members' roles and remove members"),
    ("roles.read", "View roles and their permissions"),
    ("audit.read", "View the organisation audit log"),
    ("dashboard.read", "View the operations overview"),
]

TENANT_TABLES = ["role_permissions", "invitations"]


def _seed_permissions() -> None:
    table = sa.table(
        "permissions", sa.column("key", sa.String), sa.column("description", sa.String)
    )
    op.bulk_insert(table, [{"key": k, "description": d} for k, d in PERMISSIONS])


def _row_level_security() -> None:
    """Database backstop for tenant isolation (ADR 0004).

    The application sets ``app.current_user_id`` and ``app.current_org_id`` with SET LOCAL at the
    start of each transaction. Unset settings evaluate to NULL, so queries fail closed (no rows).
    RLS is ENABLEd, not FORCEd: the schema owner (migrations, SECURITY DEFINER lookups) bypasses
    it; the runtime role ``operon_app`` never does.
    """
    op.execute("""
        CREATE FUNCTION app_current_org() RETURNS uuid LANGUAGE sql STABLE AS
        $$ SELECT nullif(current_setting('app.current_org_id', true), '')::uuid $$;
        CREATE FUNCTION app_current_user() RETURNS uuid LANGUAGE sql STABLE AS
        $$ SELECT nullif(current_setting('app.current_user_id', true), '')::uuid $$;
    """)

    for table in TENANT_TABLES:
        op.execute(f"""
            ALTER TABLE {table} ENABLE ROW LEVEL SECURITY;
            CREATE POLICY tenant_isolation ON {table}
              USING (organisation_id = app_current_org())
              WITH CHECK (organisation_id = app_current_org());
        """)

    # Members: a user can always read their own memberships (to list their organisations);
    # every write is limited to the current organisation.
    op.execute("""
        ALTER TABLE organisation_members ENABLE ROW LEVEL SECURITY;
        CREATE POLICY members_select ON organisation_members FOR SELECT
          USING (organisation_id = app_current_org() OR user_id = app_current_user());
        CREATE POLICY members_insert ON organisation_members FOR INSERT
          WITH CHECK (organisation_id = app_current_org());
        CREATE POLICY members_update ON organisation_members FOR UPDATE
          USING (organisation_id = app_current_org())
          WITH CHECK (organisation_id = app_current_org());
        CREATE POLICY members_delete ON organisation_members FOR DELETE
          USING (organisation_id = app_current_org());
    """)

    # Roles: as members — your own roles are readable across organisations (for the organisation
    # switcher); all writes stay within the current organisation.
    op.execute("""
        ALTER TABLE roles ENABLE ROW LEVEL SECURITY;
        CREATE POLICY roles_select ON roles FOR SELECT
          USING (organisation_id = app_current_org() OR id IN (
            SELECT role_id FROM organisation_members WHERE user_id = app_current_user()));
        CREATE POLICY roles_insert ON roles FOR INSERT
          WITH CHECK (organisation_id = app_current_org());
        CREATE POLICY roles_update ON roles FOR UPDATE
          USING (organisation_id = app_current_org())
          WITH CHECK (organisation_id = app_current_org());
        CREATE POLICY roles_delete ON roles FOR DELETE
          USING (organisation_id = app_current_org());
    """)

    # Organisations: visible if current, or if the user is a member; writable only when current.
    op.execute("""
        ALTER TABLE organisations ENABLE ROW LEVEL SECURITY;
        CREATE POLICY organisations_select ON organisations FOR SELECT
          USING (id = app_current_org() OR id IN (
            SELECT organisation_id FROM organisation_members WHERE user_id = app_current_user()));
        CREATE POLICY organisations_insert ON organisations FOR INSERT
          WITH CHECK (id = app_current_org());
        CREATE POLICY organisations_update ON organisations FOR UPDATE
          USING (id = app_current_org()) WITH CHECK (id = app_current_org());
        CREATE POLICY organisations_delete ON organisations FOR DELETE
          USING (id = app_current_org());
    """)

    # Audit: read only your organisation's trail; account-level events (NULL org) are write-only.
    op.execute("""
        ALTER TABLE audit_logs ENABLE ROW LEVEL SECURITY;
        CREATE POLICY audit_select ON audit_logs FOR SELECT
          USING (organisation_id = app_current_org());
        CREATE POLICY audit_insert ON audit_logs FOR INSERT
          WITH CHECK (organisation_id IS NULL OR organisation_id = app_current_org());
    """)

    # Invitation acceptance starts from a token, before the organisation is known. This lookup
    # returns only the row matching an unguessable token hash.
    op.execute("""
        CREATE FUNCTION operon_invitation_by_token(p_token_hash text)
        RETURNS TABLE (id uuid, organisation_id uuid)
        LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public, pg_temp AS
        $$ SELECT i.id, i.organisation_id FROM invitations i WHERE i.token_hash = p_token_hash $$;
        REVOKE ALL ON FUNCTION operon_invitation_by_token(text) FROM PUBLIC;
        GRANT EXECUTE ON FUNCTION operon_invitation_by_token(text) TO operon_app;
    """)


def _grants() -> None:
    # Audit trail is append-only for the application; the permission catalogue is migration-owned.
    op.execute("REVOKE UPDATE, DELETE, TRUNCATE ON audit_logs FROM operon_app")
    op.execute("REVOKE INSERT, UPDATE, DELETE, TRUNCATE ON permissions FROM operon_app")


def downgrade() -> None:
    op.execute("DROP FUNCTION IF EXISTS operon_invitation_by_token(text)")
    # This policy references organisation_members, so it must go before that table does.
    op.execute("DROP POLICY IF EXISTS organisations_select ON organisations")
    op.execute("DROP POLICY IF EXISTS roles_select ON roles")
    op.drop_index("ix_role_permissions_organisation_id", table_name="role_permissions")
    op.drop_table("role_permissions")
    op.drop_index("ix_organisation_members_user_id", table_name="organisation_members")
    op.drop_table("organisation_members")
    op.drop_index(
        "uq_invitations_open_per_email",
        table_name="invitations",
        postgresql_where=sa.text("accepted_at IS NULL AND revoked_at IS NULL"),
    )
    op.drop_index(op.f("ix_invitations_organisation_id"), table_name="invitations")
    op.drop_table("invitations")
    op.drop_table("roles")
    op.drop_index("ix_user_sessions_user_id_active", table_name="user_sessions")
    op.drop_table("user_sessions")
    op.drop_table("user_credentials")
    op.drop_index("ix_user_action_tokens_user_purpose", table_name="user_action_tokens")
    op.drop_table("user_action_tokens")
    op.drop_index(op.f("ix_recovery_codes_user_id"), table_name="recovery_codes")
    op.drop_table("recovery_codes")
    op.drop_table("organisations")
    op.drop_table("mfa_factors")
    op.drop_table("users")
    op.drop_table("permissions")
    op.drop_index("ix_audit_logs_org_occurred", table_name="audit_logs")
    op.drop_index("ix_audit_logs_actor", table_name="audit_logs")
    op.drop_table("audit_logs")
    op.execute("DROP FUNCTION IF EXISTS app_current_org()")
    op.execute("DROP FUNCTION IF EXISTS app_current_user()")
