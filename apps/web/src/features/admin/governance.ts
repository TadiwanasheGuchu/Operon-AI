"use client";

import { useQuery } from "@tanstack/react-query";

import { useActiveOrganisation } from "@/features/session/use-session";
import { api } from "@/lib/api/client";

export type RetentionKey = "audit_days" | "conversation_days" | "run_log_days" | "sync_job_days";

export interface Retention extends Record<RetentionKey, number> {
  bounds: Record<RetentionKey, [number, number]>;
}

export interface SsoDomain {
  domain: string;
  verified: boolean;
  txt_name: string;
  txt_value: string;
}

export type SsoRole = "operations_manager" | "approver" | "analyst" | "viewer";

export interface SsoSettings {
  configured: boolean;
  issuer: string | null;
  client_id: string | null;
  has_client_secret: boolean;
  enabled: boolean;
  enforce: boolean;
  jit_provisioning: boolean;
  default_role_key: SsoRole;
  redirect_uri: string;
  domains: SsoDomain[];
}

export function useRetention() {
  const org = useActiveOrganisation();
  return useQuery({
    queryKey: ["tenant", org?.id, "retention"],
    queryFn: () => api.get<Retention>("/organisations/current/retention"),
    enabled: Boolean(org),
  });
}

export function useSso() {
  const org = useActiveOrganisation();
  return useQuery({
    queryKey: ["tenant", org?.id, "sso"],
    queryFn: () => api.get<SsoSettings>("/organisations/current/sso"),
    enabled: Boolean(org),
  });
}

/** Downloads the organisation export (a ZIP) through the browser. */
export async function downloadExport(): Promise<void> {
  const blob = await api.post<Blob>("/organisations/current/export", undefined, { blob: true });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `operon-export-${new Date().toISOString().slice(0, 10)}.zip`;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}
