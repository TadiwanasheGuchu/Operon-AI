"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { useTenantMutation } from "@/features/admin/api";
import { useActiveOrganisation } from "@/features/session/use-session";
import { api } from "@/lib/api/client";

export interface Availability {
  available: boolean;
  reason: string | null;
  provider: string | null;
  model: string | null;
  tools: string[];
}

export interface Citation {
  ref: string;
  label: string;
  kind: "insight" | "incident" | "purchase_request" | "purchase_order" | "product" | string;
  href: string | null;
}

export interface Message {
  id: string;
  role: "user" | "assistant";
  content: string;
  citations: Citation[];
  checked: boolean;
  problems: string[];
  execution_id: string | null;
  created_at: string;
}

export interface ConversationSummary {
  id: string;
  title: string;
  updated_at: string;
}

export interface ConversationDetail extends ConversationSummary {
  messages: Message[];
}

export type RunStatus = "running" | "succeeded" | "limited" | "refused" | "failed";

export interface Run {
  id: string;
  kind: "assistant" | "agent";
  trigger: "chat" | "manual" | "schedule";
  status: RunStatus;
  agent_version: number | null;
  provider: string;
  model: string;
  prompt_version: string;
  tools_offered: string[];
  steps: number;
  tool_calls: number;
  input_tokens: number;
  output_tokens: number;
  summary: string | null;
  stop_reason: string | null;
  error: string | null;
  started_at: string;
  finished_at: string | null;
  triggered_by_name: string | null;
}

export interface Step {
  position: number;
  kind: "model_turn" | "tool_call" | "tool_denied" | "tool_error" | "limit" | "refused" | "final" | "error";
  tool_name: string | null;
  input: Record<string, unknown> | null;
  output: Record<string, unknown> | null;
  message: string | null;
  input_tokens: number;
  output_tokens: number;
  latency_ms: number;
  created_at: string;
}

export interface RunDetail extends Run {
  log: Step[];
}

export interface AgentTool {
  name: string;
  description: string;
  permission: string;
  writes: boolean;
  enabled: boolean;
  run_as_permitted: boolean | null;
}

export interface AgentLimits {
  max_steps: number;
  max_tool_calls: number;
  max_tokens: number;
  max_seconds: number;
}

export interface AgentParams {
  guidance: string;
  min_severity: "medium" | "high" | "critical";
  max_drafts: number;
  limits: AgentLimits;
}

export interface AgentConfig {
  key: string;
  name: string;
  enabled: boolean;
  schedule: "off" | "daily";
  next_run_at: string | null;
  run_as_user_id: string | null;
  run_as_name: string | null;
  current_version: number;
  params: AgentParams;
  tools: AgentTool[];
  availability: Availability;
}

function useKey(...parts: unknown[]) {
  const org = useActiveOrganisation();
  return { key: ["tenant", org?.id, "agents", ...parts] as const, enabled: Boolean(org), org };
}

export function useAssistantStatus(enabled: boolean) {
  const { key, enabled: ok } = useKey("assistant-status");
  return useQuery({ queryKey: key, queryFn: () => api.get<Availability>("/assistant/status"), enabled: ok && enabled });
}

export function useConversations(enabled: boolean) {
  const { key, enabled: ok } = useKey("conversations");
  return useQuery({ queryKey: key, queryFn: () => api.get<ConversationSummary[]>("/assistant/conversations"), enabled: ok && enabled });
}

export function useConversation(id: string | null) {
  const { key, enabled } = useKey("conversation", id);
  return useQuery({
    queryKey: key,
    queryFn: () => api.get<ConversationDetail>(`/assistant/conversations/${id}`),
    enabled: enabled && Boolean(id),
  });
}

export function useAsk() {
  const queryClient = useQueryClient();
  const { org } = useKey();
  return useMutation({
    mutationFn: (v: { question: string; conversation_id: string | null }) =>
      api.post<{ conversation_id: string; message: Message }>("/assistant/messages", v),
    onSuccess: (r) =>
      Promise.all([
        queryClient.invalidateQueries({ queryKey: ["tenant", org?.id, "agents", "conversation", r.conversation_id] }),
        queryClient.invalidateQueries({ queryKey: ["tenant", org?.id, "agents", "conversations"] }),
      ]),
  });
}

export function useAgentConfig() {
  const { key, enabled } = useKey("config");
  return useQuery({ queryKey: key, queryFn: () => api.get<AgentConfig>("/agents/inventory-replenishment"), enabled });
}

export function useRuns() {
  const { key, enabled } = useKey("runs");
  return useQuery({
    queryKey: key,
    queryFn: () => api.get<Run[]>("/agents/runs?limit=20"),
    enabled,
    refetchInterval: (q) => (q.state.data?.some((r) => r.status === "running") ? 3000 : false),
  });
}

export function useRun(id: string) {
  const { key, enabled } = useKey("run", id);
  return useQuery({
    queryKey: key,
    queryFn: () => api.get<RunDetail>(`/agents/runs/${id}`),
    enabled,
    refetchInterval: (q) => (q.state.data?.status === "running" ? 2000 : false),
  });
}

export function useAgentMutation<TVars, TResult = unknown>(fn: (v: TVars) => Promise<TResult>) {
  return useTenantMutation(fn, ["agents", "workflows", "insights", "notifications"]);
}

export const RUN_STATUS_LABEL: Record<RunStatus, string> = {
  running: "Running",
  succeeded: "Finished",
  limited: "Stopped at a limit",
  refused: "Declined by the model",
  failed: "Failed",
};

export const TOOL_LABEL: Record<string, string> = {
  list_insights: "List insights",
  get_insight: "Read an insight and its evidence",
  search_stock: "Look up stock and recent sales",
  list_purchase_orders: "List purchase orders",
  list_incidents: "List incidents",
  list_purchase_requests: "List purchase requests",
  draft_purchase_request: "Draft a purchase request (sent for approval)",
};
