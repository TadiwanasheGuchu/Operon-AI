"use client";

import { useQuery } from "@tanstack/react-query";

import { useTenantMutation } from "@/features/admin/api";
import type { Severity } from "@/features/dashboard/contract";
import { useActiveOrganisation } from "@/features/session/use-session";
import { api } from "@/lib/api/client";

export type InsightStatus = "open" | "acknowledged" | "actioned" | "resolved" | "dismissed";
export type InsightFilter = "active" | "closed" | "all";

export interface Person {
  user_id: string;
  full_name: string;
  email: string;
}

export interface InsightSummary {
  id: string;
  reference: string;
  rule_id: string;
  rule_version: number;
  category: string;
  severity: Severity;
  confidence: "normal" | "low";
  status: InsightStatus;
  title: string;
  summary: string;
  subject_label: string;
  owner: Person | null;
  detected_at: string;
  last_evaluated_at: string;
  incident_id: string | null;
}

export interface InsightList {
  items: InsightSummary[];
  total: number;
  limit: number;
  offset: number;
  active_by_severity: Partial<Record<Severity, number>>;
}

export interface Evidence {
  id: string;
  key: string;
  label: string;
  value: string;
  unit: string | null;
  source_type: string;
  source_id: string | null;
  source_ref: string | null;
  connection: { id: string; name: string; connector: string } | null;
  observed_at: string | null;
  formula: string | null;
  resolvable: boolean;
}

export interface InsightEvent {
  id: string;
  kind: string;
  actor_label: string;
  details: Record<string, unknown>;
  created_at: string;
}

export interface Recommendation {
  action: "create_purchase_request" | "contact_supplier" | string;
  quantity?: number;
  quantity_display?: string;
  supplier_name?: string | null;
  estimated_value_display?: string;
  purchase_order_number?: string;
  basis?: string;
  [key: string]: unknown;
}

export interface InsightDetail extends InsightSummary {
  metrics: Record<string, string>;
  recommendation: Recommendation | null;
  recommended_action: string;
  assumptions: string[];
  limitations: string[];
  explanation: {
    what_happened: string;
    why_it_matters: string;
    source: "template" | "model";
    provider: string | null;
    model: string | null;
    generated_at: string | null;
    pending: boolean;
  };
  evidence: Evidence[];
  events: InsightEvent[];
  closed_at: string | null;
  close_reason: string | null;
  suppressed_until: string | null;
  allowed_transitions: InsightStatus[];
}

export interface SourceRecord {
  source_type: string;
  source_id: string;
  external_id: string | null;
  connection: { id: string; name: string; connector: string } | null;
  updated_at: string | null;
  fields: Record<string, unknown>;
}

export interface DetectorParam {
  name: string;
  description: string | null;
  type: "integer" | "number" | "string" | "choice" | string;
  default: unknown;
  value: unknown;
  minimum: number | null;
  maximum: number | null;
  choices: string[] | null;
}

export interface Detector {
  rule_id: string;
  version: number;
  name: string;
  category: string;
  description: string;
  enabled: boolean;
  params: DetectorParam[];
  updated_at: string | null;
}

export interface DetectionRun {
  id: string;
  trigger: "sync" | "upload" | "manual" | "schedule";
  status: "running" | "succeeded" | "failed";
  as_of: string;
  started_at: string;
  finished_at: string | null;
  stats: Record<string, Record<string, number | boolean | string>>;
  error: string | null;
}

export interface AISettings {
  enabled: boolean;
  provider: "anthropic" | "openai";
  provider_available: boolean;
  model: string | null;
  monthly_token_budget: number;
  tokens_used_this_month: number;
  available_providers: string[];
  data_shared: string;
}

function useKey(...parts: unknown[]) {
  const org = useActiveOrganisation();
  return { key: ["tenant", org?.id, "insights", ...parts] as const, enabled: Boolean(org) };
}

export const PAGE_SIZE = 25;

export function useInsights(filter: InsightFilter, severity: Severity | "", page: number) {
  const { key, enabled } = useKey("list", filter, severity, page);
  const params = new URLSearchParams({ status: filter, limit: String(PAGE_SIZE), offset: String(page * PAGE_SIZE) });
  if (severity) params.set("severity", severity);
  return useQuery({ queryKey: key, queryFn: () => api.get<InsightList>(`/insights?${params}`), enabled });
}

export function useInsight(id: string) {
  const { key, enabled } = useKey("detail", id);
  return useQuery({
    queryKey: key,
    queryFn: () => api.get<InsightDetail>(`/insights/${id}`),
    enabled,
    // While a model is writing the explanation, check back until it lands.
    refetchInterval: (q) => (q.state.data?.explanation.pending ? 4000 : false),
  });
}

export function useSourceRecord(insightId: string, evidenceId: string | null) {
  const { key, enabled } = useKey("source", insightId, evidenceId);
  return useQuery({
    queryKey: key,
    queryFn: () => api.get<SourceRecord>(`/insights/${insightId}/evidence/${evidenceId}/source`),
    enabled: enabled && Boolean(evidenceId),
  });
}

export function useDetectors() {
  const { key, enabled } = useKey("detectors");
  return useQuery({ queryKey: key, queryFn: () => api.get<Detector[]>("/intelligence/detectors"), enabled });
}

export function useDetectionRuns() {
  const { key, enabled } = useKey("runs");
  return useQuery({ queryKey: key, queryFn: () => api.get<DetectionRun[]>("/intelligence/runs?limit=5"), enabled });
}

export function useAISettings() {
  const { key, enabled } = useKey("ai");
  return useQuery({ queryKey: key, queryFn: () => api.get<AISettings>("/intelligence/ai-settings"), enabled });
}

/** Any change to insights can change the dashboard and incidents too. */
export function useInsightMutation<TVars, TResult = unknown>(fn: (v: TVars) => Promise<TResult>) {
  return useTenantMutation(fn, ["insights", "incidents", "dashboard", "notifications"]);
}

export const RULE_LABEL: Record<string, string> = {
  "inventory.stockout_risk": "Stockout risk",
  "procurement.po_overdue": "Overdue purchase order",
};

export const STATUS_LABEL: Record<InsightStatus, string> = {
  open: "Open",
  acknowledged: "Acknowledged",
  actioned: "Actioned",
  resolved: "Resolved",
  dismissed: "Dismissed",
};
