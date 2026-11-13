"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { useActiveOrganisation } from "@/features/session/use-session";
import { api } from "@/lib/api/client";

export interface Member {
  id: string;
  user_id: string;
  email: string;
  full_name: string;
  role_key: string;
  role_name: string;
  joined_at: string;
  mfa_enabled: boolean;
  is_you: boolean;
}

export interface PendingInvitation {
  id: string;
  email: string;
  role_key: string;
  role_name: string;
  invited_by: string | null;
  created_at: string;
  expires_at: string;
}

export interface Role {
  id: string;
  key: string;
  name: string;
  description: string;
  is_system: boolean;
  permissions: string[];
  assignable_by_you: boolean;
}

export interface PermissionInfo {
  key: string;
  description: string;
}

export interface AuditEvent {
  id: string;
  occurred_at: string;
  actor_type: string;
  actor_user_id: string | null;
  actor_label: string;
  action: string;
  target_type: string | null;
  target_id: string | null;
  outcome: "success" | "failure" | "denied";
  details: Record<string, unknown>;
  request_id: string | null;
}

/** Tenant-scoped query key: switching organisation discards everything under "tenant". */
function useTenantKey(...parts: unknown[]) {
  const org = useActiveOrganisation();
  return { key: ["tenant", org?.id, ...parts] as const, enabled: Boolean(org) };
}

/** Pass `allowed=false` when the user lacks members.read, so no doomed request is made. */
export function useMembers(allowed = true) {
  const { key, enabled } = useTenantKey("members");
  return useQuery({ queryKey: key, queryFn: () => api.get<Member[]>("/members"), enabled: enabled && allowed });
}

export function useInvitations(enabledByPermission = true) {
  const { key, enabled } = useTenantKey("invitations");
  return useQuery({
    queryKey: key,
    queryFn: () => api.get<PendingInvitation[]>("/invitations"),
    enabled: enabled && enabledByPermission,
  });
}

export function useRoles(enabledByPermission = true) {
  const { key, enabled } = useTenantKey("roles");
  return useQuery({ queryKey: key, queryFn: () => api.get<Role[]>("/roles"), enabled: enabled && enabledByPermission });
}

export function usePermissionCatalogue() {
  return useQuery({ queryKey: ["permissions"], queryFn: () => api.get<PermissionInfo[]>("/permissions", { tenant: false }) });
}

/** Mutation that refreshes the given tenant collections afterwards. */
export function useTenantMutation<TVars, TResult = unknown>(
  fn: (vars: TVars) => Promise<TResult>,
  invalidate: string[],
) {
  const queryClient = useQueryClient();
  const org = useActiveOrganisation();
  return useMutation({
    mutationFn: fn,
    onSettled: () =>
      Promise.all(
        invalidate.map((k) => queryClient.invalidateQueries({ queryKey: ["tenant", org?.id, k] })),
      ),
  });
}
