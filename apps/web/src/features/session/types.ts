export interface SessionUser {
  id: string;
  email: string;
  full_name: string;
  email_verified: boolean;
  mfa_enabled: boolean;
  created_at: string;
}

export interface OrganisationSummary {
  id: string;
  name: string;
  role_key: string;
  role_name: string;
  mfa_required: boolean;
  is_demo: boolean;
}

export interface SessionState {
  user: SessionUser | null;
  organisations: OrganisationSummary[];
}

export interface CurrentOrganisation {
  id: string;
  name: string;
  mfa_required: boolean;
  is_demo: boolean;
  created_at: string;
  role_key: string;
  permissions: string[];
}

export type Permission =
  | "organisation.read"
  | "organisation.manage"
  | "members.read"
  | "members.invite"
  | "members.manage"
  | "roles.read"
  | "audit.read"
  | "dashboard.read"
  | "integrations.read"
  | "integrations.manage"
  | "insights.read"
  | "insights.manage"
  | "incidents.read"
  | "incidents.manage"
  | "workflows.read"
  | "workflows.request"
  | "workflows.manage"
  | "approvals.decide";
