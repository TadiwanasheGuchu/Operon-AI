"use client";

import { useQuery } from "@tanstack/react-query";

import { useTenantMutation } from "@/features/admin/api";
import type { Person } from "@/features/intelligence/api";
import { useActiveOrganisation } from "@/features/session/use-session";
import { api } from "@/lib/api/client";

export type ExecutionStatus =
  | "awaiting_approval"
  | "approved"
  | "executing"
  | "completed"
  | "rejected"
  | "expired"
  | "failed"
  | "cancelled";
export type ExecutionFilter = "active" | "finished" | "all";

export interface Approval {
  id: string;
  stage: number;
  name: string;
  approver_roles: string[];
  approver_role_names: string[];
  reason: string;
  status: "waiting" | "pending" | "approved" | "rejected" | "expired" | "cancelled";
  due_at: string | null;
  escalated_at: string | null;
  decided_by: Person | null;
  decided_at: string | null;
  comment: string | null;
  blocked_reason: string | null;
}

export interface ExecutionSummary {
  id: string;
  reference: string;
  title: string;
  status: ExecutionStatus;
  requested_by: Person | null;
  supplier_name: string | null;
  value_display: string | null;
  insight_id: string | null;
  insight_reference: string | null;
  current_stage: string | null;
  target: "odoo" | "record_only";
  external_reference: string | null;
  created_at: string;
  updated_at: string;
  completed_at: string | null;
}

export interface ExecutionList {
  items: ExecutionSummary[];
  total: number;
  limit: number;
  offset: number;
  by_status: Partial<Record<ExecutionStatus, number>>;
}

export interface ExecutionEvent {
  id: string;
  kind: string;
  actor_label: string;
  message: string;
  details: Record<string, unknown>;
  created_at: string;
}

export interface ExecutionDetail extends ExecutionSummary {
  input: {
    product_name: string;
    sku: string | null;
    uom: string;
    location_name: string | null;
    supplier_name: string | null;
    quantity: number;
    recommended_quantity: number | null;
    unit_price: string | null;
    currency: string | null;
    value_display: string | null;
    note: string;
    insight_reference: string | null;
    target_name: string | null;
    target_reason: string | null;
  };
  result: { mode?: string; reference?: string; external_id?: string; state?: string; note?: string };
  error: string | null;
  attempts: number;
  policy_version: number;
  approvals: Approval[];
  events: ExecutionEvent[];
  can_cancel: boolean;
  can_retry: boolean;
}

export interface InboxItem {
  approval: Approval;
  execution: ExecutionSummary;
}

export interface StageRule {
  name: string;
  min_value: string;
  approver_roles: string[];
}

export interface PurchaseRequestParams {
  currency: string;
  stages: StageRule[];
  approval_timeout_hours: number;
  max_attempts: number;
}

export interface WorkflowConfig {
  key: string;
  name: string;
  enabled: boolean;
  current_version: number;
  params: PurchaseRequestParams;
  versions: { version: number; params: PurchaseRequestParams; created_at: string; created_by: Person | null }[];
  role_names: Record<string, string>;
}

export const PAGE_SIZE = 25;

function useKey(...parts: unknown[]) {
  const org = useActiveOrganisation();
  return { key: ["tenant", org?.id, "workflows", ...parts] as const, enabled: Boolean(org) };
}

export function useExecutions(filter: ExecutionFilter, mine: boolean, page: number) {
  const { key, enabled } = useKey("list", filter, mine, page);
  const params = new URLSearchParams({ status: filter, limit: String(PAGE_SIZE), offset: String(page * PAGE_SIZE) });
  if (mine) params.set("mine", "true");
  return useQuery({ queryKey: key, queryFn: () => api.get<ExecutionList>(`/purchase-requests?${params}`), enabled });
}

const MOVING: ExecutionStatus[] = ["approved", "executing"];

export function useExecution(id: string) {
  const { key, enabled } = useKey("detail", id);
  return useQuery({
    queryKey: key,
    queryFn: () => api.get<ExecutionDetail>(`/purchase-requests/${id}`),
    enabled,
    // While it's being sent to the purchasing system, check back until it settles.
    refetchInterval: (q) => (q.state.data && MOVING.includes(q.state.data.status) ? 3000 : false),
  });
}

export function useInbox() {
  const { key, enabled } = useKey("inbox");
  return useQuery({ queryKey: key, queryFn: () => api.get<InboxItem[]>("/approvals"), enabled });
}

export function useWorkflowConfig() {
  const { key, enabled } = useKey("config");
  return useQuery({ queryKey: key, queryFn: () => api.get<WorkflowConfig>("/workflows/purchase-requests"), enabled });
}

export function useWorkflowMutation<TVars, TResult = unknown>(fn: (v: TVars) => Promise<TResult>) {
  return useTenantMutation(fn, ["workflows", "insights", "dashboard", "notifications"]);
}

export const EXECUTION_STATUS_LABEL: Record<ExecutionStatus, string> = {
  awaiting_approval: "Awaiting approval",
  approved: "Approved",
  executing: "Sending",
  completed: "Completed",
  rejected: "Rejected",
  expired: "Expired",
  failed: "Failed",
  cancelled: "Cancelled",
};
