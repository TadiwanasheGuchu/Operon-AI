/**
 * Contract for GET /api/v1/dashboard/summary — mirrors apps/api/.../dashboard/schemas.py.
 * Responses are validated at runtime so contract drift fails loudly instead of rendering wrongly.
 */
import { z } from "zod";

export const periods = ["7d", "30d", "90d"] as const;
export type Period = (typeof periods)[number];

export const provenanceSchema = z.enum(["live", "demo", "stale", "unavailable"]);
export type Provenance = z.infer<typeof provenanceSchema>;

export const severitySchema = z.enum(["critical", "high", "medium", "low"]);
export type Severity = z.infer<typeof severitySchema>;

export const sectionKeys = [
  "getting_started",
  "insights",
  "approvals",
  "incidents",
  "fill_rate",
  "inventory_risk",
  "workflows",
  "integrations",
  "activity",
  "team",
] as const;
export type SectionKey = (typeof sectionKeys)[number];

function section<T extends z.ZodType>(data: T) {
  return z.object({
    state: z.enum(["ready", "unavailable", "restricted"]),
    provenance: provenanceSchema,
    as_of: z.iso.datetime({ offset: true }).nullable(),
    message: z.string().nullable(),
    available_in_phase: z.number().int().nullable(),
    data: data.nullable(),
  });
}
export type Section<T> = {
  state: "ready" | "unavailable" | "restricted";
  provenance: Provenance;
  as_of: string | null;
  message: string | null;
  available_in_phase: number | null;
  data: T | null;
};

const datetime = z.iso.datetime({ offset: true });

export const indicatorSchema = z.object({
  key: z.string(),
  label: z.string(),
  value: z.number().int().nullable(),
  total: z.number().int().nullable(),
  previous_value: z.number().int().nullable(),
  increase_is: z.enum(["good", "bad", "neutral"]),
  state: z.enum(["healthy", "attention", "critical", "neutral"]),
  detail: z.string(),
  provenance: provenanceSchema,
});
export type Indicator = z.infer<typeof indicatorSchema>;

export const insightSchema = z.object({
  id: z.string(),
  ref: z.string(),
  title: z.string(),
  category: z.enum(["inventory", "procurement", "finance", "operations"]),
  severity: severitySchema,
  status: z.enum(["open", "acknowledged", "actioned", "resolved", "dismissed"]),
  detected_at: datetime,
  owner: z.string().nullable(),
  source_system: z.string(),
  rule_id: z.string(),
  rule_version: z.number().int(),
  summary: z.string(),
  why_it_matters: z.string(),
  recommended_action: z.string(),
  assumptions: z.array(z.string()),
  limitations: z.array(z.string()),
  evidence: z.array(z.object({ label: z.string(), value: z.string(), source: z.string().nullable() })).min(1),
  explanation_generated_by: z.enum(["model", "template"]),
  explanation_model: z.string().nullable(),
});
export type Insight = z.infer<typeof insightSchema>;

export const approvalSchema = z.object({
  id: z.string(),
  ref: z.string(),
  title: z.string(),
  requester: z.string(),
  amount: z.number().nonnegative().nullable(),
  currency: z.string().length(3).nullable(),
  policy: z.string(),
  requested_at: datetime,
  related_insight_ref: z.string().nullable(),
});
export type Approval = z.infer<typeof approvalSchema>;

export const activityEventSchema = z.object({
  id: z.string(),
  at: datetime,
  actor_type: z.enum(["system", "user", "integration", "agent"]),
  actor: z.string(),
  message: z.string(),
  ref: z.string().nullable(),
});
export type ActivityEvent = z.infer<typeof activityEventSchema>;

export const integrationStatusSchema = z.object({
  id: z.string(),
  name: z.string(),
  system: z.string(),
  status: z.enum(["healthy", "degraded", "disconnected", "paused"]),
  last_sync_at: datetime.nullable(),
  detail: z.string(),
});
export type IntegrationStatus = z.infer<typeof integrationStatusSchema>;

export const workflowStatusSchema = z.object({
  workflow: z.string(),
  running: z.number().int(),
  awaiting_approval: z.number().int(),
  failed_24h: z.number().int(),
  completed: z.number().int(),
  success_rate: z.number(),
});
export type WorkflowStatus = z.infer<typeof workflowStatusSchema>;

export const fillRateSchema = z.object({
  target: z.number(),
  points: z.array(z.object({ date: z.iso.date(), value: z.number() })),
});
export type FillRate = z.infer<typeof fillRateSchema>;

export const locationRiskSchema = z.object({
  location: z.string(),
  skus_at_risk: z.number().int(),
  skus_tracked: z.number().int().positive(),
});
export type LocationRisk = z.infer<typeof locationRiskSchema>;

export const incidentCountsSchema = z.object({
  critical: z.number().int(),
  high: z.number().int(),
  medium: z.number().int(),
  low: z.number().int(),
});
export type IncidentCounts = z.infer<typeof incidentCountsSchema>;

export const setupStepSchema = z.object({
  key: z.string(),
  title: z.string(),
  body: z.string(),
  done: z.boolean(),
  available: z.boolean(),
  href: z.string().nullable(),
  action_label: z.string().nullable(),
});
export type SetupStep = z.infer<typeof setupStepSchema>;

export const teamSchema = z.object({
  members: z.number().int(),
  pending_invitations: z.number().int(),
  mfa_enabled: z.number().int(),
  recent_joins: z.array(z.object({ name: z.string(), role_name: z.string(), joined_at: datetime })),
});
export type Team = z.infer<typeof teamSchema>;

export const layoutSchema = z.object({
  preset: z.string(),
  name: z.string(),
  is_default: z.boolean(),
  sections: z.array(z.object({ key: z.enum(sectionKeys), size: z.enum(["wide", "narrow"]) })),
});
export type Layout = z.infer<typeof layoutSchema>;

export const dashboardSummarySchema = z.object({
  organisation: z.object({ id: z.string(), name: z.string(), is_demo: z.boolean() }),
  viewer: z.object({ name: z.string(), role_key: z.string(), role_name: z.string() }),
  layout: layoutSchema,
  period: z.enum(periods),
  generated_at: datetime,
  indicators: z.array(indicatorSchema),
  getting_started: section(z.array(setupStepSchema)),
  insights: section(z.array(insightSchema)),
  approvals: section(z.array(approvalSchema)),
  incidents: section(incidentCountsSchema),
  fill_rate: section(fillRateSchema),
  inventory_risk: section(z.array(locationRiskSchema)),
  workflows: section(z.array(workflowStatusSchema)),
  integrations: section(z.array(integrationStatusSchema)),
  activity: section(z.array(activityEventSchema)),
  team: section(teamSchema),
});
export type DashboardSummary = z.infer<typeof dashboardSummarySchema>;

export const layoutSettingsSchema = z.object({
  current: layoutSchema,
  default_preset: z.string(),
  presets: z.array(z.object({ key: z.string(), name: z.string(), description: z.string() })),
});
export type LayoutSettings = z.infer<typeof layoutSettingsSchema>;
