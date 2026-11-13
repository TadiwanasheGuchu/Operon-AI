"use client";

import { useQuery } from "@tanstack/react-query";

import type { Severity } from "@/features/dashboard/contract";
import type { Person } from "@/features/intelligence/api";
import { useTenantMutation } from "@/features/admin/api";
import { useActiveOrganisation } from "@/features/session/use-session";
import { api } from "@/lib/api/client";

export type IncidentStatus = "open" | "investigating" | "resolved";
export type IncidentFilter = "unresolved" | "resolved" | "all";

export interface IncidentSummary {
  id: string;
  reference: string;
  title: string;
  severity: Severity;
  status: IncidentStatus;
  assignee: Person | null;
  insight: { id: string; reference: string; title: string; status: string; severity: Severity } | null;
  response_due_at: string;
  response_overdue: boolean;
  escalation_level: number;
  created_at: string;
  updated_at: string;
  resolved_at: string | null;
}

export interface IncidentList {
  items: IncidentSummary[];
  total: number;
  limit: number;
  offset: number;
  unresolved_by_severity: Partial<Record<Severity, number>>;
}

export interface IncidentEvent {
  id: string;
  kind: "created" | "comment" | "assigned" | "status_changed" | "severity_changed" | "escalated" | "insight_linked";
  actor_label: string;
  body: string | null;
  details: Record<string, unknown>;
  created_at: string;
}

export interface IncidentDetail extends IncidentSummary {
  description: string;
  resolution: string | null;
  reported_by: Person | null;
  events: IncidentEvent[];
  allowed_transitions: IncidentStatus[];
}

export const PAGE_SIZE = 25;

function useKey(...parts: unknown[]) {
  const org = useActiveOrganisation();
  return { key: ["tenant", org?.id, "incidents", ...parts] as const, enabled: Boolean(org) };
}

export function useIncidents(filter: IncidentFilter, assignee: "" | "me" | "none", page: number) {
  const { key, enabled } = useKey("list", filter, assignee, page);
  const params = new URLSearchParams({ status: filter, limit: String(PAGE_SIZE), offset: String(page * PAGE_SIZE) });
  if (assignee) params.set("assignee", assignee);
  return useQuery({ queryKey: key, queryFn: () => api.get<IncidentList>(`/incidents?${params}`), enabled });
}

export function useIncident(id: string) {
  const { key, enabled } = useKey("detail", id);
  return useQuery({ queryKey: key, queryFn: () => api.get<IncidentDetail>(`/incidents/${id}`), enabled });
}

export function useIncidentMutation<TVars, TResult = unknown>(fn: (v: TVars) => Promise<TResult>) {
  return useTenantMutation(fn, ["incidents", "insights", "dashboard", "notifications"]);
}

export const INCIDENT_STATUS_LABEL: Record<IncidentStatus, string> = {
  open: "Open",
  investigating: "Investigating",
  resolved: "Resolved",
};

/** Response targets mirrored from the API (incidents/service.py RESPONSE_TARGETS). */
export const RESPONSE_TARGET_LABEL: Record<Severity, string> = {
  critical: "1 hour",
  high: "4 hours",
  medium: "24 hours",
  low: "72 hours",
};
