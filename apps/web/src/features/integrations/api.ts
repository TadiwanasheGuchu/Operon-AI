"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { useActiveOrganisation } from "@/features/session/use-session";
import { api, apiRequest } from "@/lib/api/client";

export type ConnectorKey = "odoo" | "shopify" | "csv";
export type ConnectionStatus = "active" | "syncing" | "degraded" | "action_required" | "paused";
export type ImportKind = "locations" | "products" | "supplier_terms" | "stock" | "sales" | "purchase_orders";

export interface CatalogueField {
  name: string;
  label: string;
  secret: boolean;
  required: boolean;
  help: string | null;
  choices: string[] | null;
}

export interface CatalogueEntry {
  key: ConnectorKey;
  name: string;
  description: string;
  provides: string[];
  fields: CatalogueField[];
  supports_webhooks: boolean;
  verified_live: boolean;
  verification_note: string;
}

export interface Connection {
  id: string;
  connector: ConnectorKey;
  name: string;
  status: ConnectionStatus;
  config: Record<string, string>;
  sync_interval_minutes: number;
  last_sync_at: string | null;
  last_success_at: string | null;
  last_error: string | null;
  created_at: string;
  webhook_url: string | null;
  has_webhook_secret: boolean;
}

export interface SyncJob {
  id: string;
  trigger: "initial" | "schedule" | "manual" | "webhook" | "upload";
  status: "running" | "succeeded" | "failed";
  started_at: string;
  finished_at: string | null;
  stats: Record<string, { received?: number; written?: number; skipped?: number; file?: string }>;
  error: string | null;
}

export interface InboundEvent {
  id: string;
  source_event_id: string;
  topic: string;
  status: "pending" | "processed" | "ignored";
  received_at: string;
  processed_at: string | null;
}

export interface UploadResult {
  kind: ImportKind;
  accepted: boolean;
  rows: number;
  written: number;
  error_count: number;
  errors: { row: number; column: string | null; message: string }[];
}

function useKey(...parts: unknown[]) {
  const org = useActiveOrganisation();
  return { key: ["tenant", org?.id, "integrations", ...parts] as const, enabled: Boolean(org), org };
}

export function useCatalogue() {
  const { key, enabled } = useKey("catalogue");
  return useQuery({ queryKey: key, queryFn: () => api.get<CatalogueEntry[]>("/integrations/catalogue"), enabled, staleTime: Infinity });
}

export function useConnections() {
  const { key, enabled } = useKey("list");
  return useQuery({ queryKey: key, queryFn: () => api.get<Connection[]>("/integrations"), enabled });
}

export function useConnection(id: string) {
  const { key, enabled } = useKey("detail", id);
  return useQuery({
    queryKey: key,
    queryFn: () => api.get<Connection>(`/integrations/${id}`),
    enabled,
    // Poll while a sync is in progress so the page settles on the result.
    refetchInterval: (q) => (q.state.data?.status === "syncing" ? 3000 : false),
  });
}

export function useSyncJobs(id: string) {
  const { key, enabled } = useKey("jobs", id);
  return useQuery({ queryKey: key, queryFn: () => api.get<SyncJob[]>(`/integrations/${id}/sync-jobs?limit=20`), enabled });
}

export function useEvents(id: string, enabledFor: boolean) {
  const { key, enabled } = useKey("events", id);
  return useQuery({ queryKey: key, queryFn: () => api.get<InboundEvent[]>(`/integrations/${id}/events?limit=20`), enabled: enabled && enabledFor });
}

/** Invalidates every integrations query (and the dashboard) after a change. */
export function useIntegrationMutation<TVars, TResult>(fn: (v: TVars) => Promise<TResult>) {
  const queryClient = useQueryClient();
  const org = useActiveOrganisation();
  return useMutation({
    mutationFn: fn,
    onSettled: () =>
      Promise.all([
        queryClient.invalidateQueries({ queryKey: ["tenant", org?.id, "integrations"] }),
        queryClient.invalidateQueries({ queryKey: ["tenant", org?.id, "dashboard"] }),
        queryClient.invalidateQueries({ queryKey: ["tenant", org?.id, "notifications"] }),
      ]),
  });
}

export async function uploadCsv(connectionId: string, kind: ImportKind, file: File): Promise<UploadResult> {
  const form = new FormData();
  form.set("kind", kind);
  form.set("file", file);
  return apiRequest<UploadResult>("POST", `/integrations/${connectionId}/uploads`, { form });
}

export const IMPORT_KINDS: { key: ImportKind; label: string; help: string }[] = [
  { key: "locations", label: "Locations", help: "Warehouses and stores. Import these first." },
  { key: "products", label: "Products", help: "One row per SKU." },
  { key: "supplier_terms", label: "Supplier terms", help: "Lead time, minimum order and price per supplier and SKU." },
  { key: "stock", label: "Stock", help: "On-hand stock per SKU and location. Replaces the previous stock import." },
  { key: "sales", label: "Sales", help: "Units sold per day and SKU. Replaces those days' values." },
  { key: "purchase_orders", label: "Purchase orders", help: "One row per order line." },
];
