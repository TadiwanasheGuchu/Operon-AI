"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useCallback, useEffect, useSyncExternalStore } from "react";

import { api, ApiRequestError } from "@/lib/api/client";

import {
  getActiveOrganisationId,
  setActiveOrganisationId,
  subscribeActiveOrganisation,
} from "./active-organisation";
import type { CurrentOrganisation, Permission, SessionState } from "./types";

export const sessionKey = ["auth", "session"] as const;

export function useSession() {
  return useQuery({
    queryKey: sessionKey,
    queryFn: () => api.get<SessionState>("/auth/session", { tenant: false }),
    staleTime: 30_000,
  });
}

/** Active organisation: the stored choice if still a membership, otherwise the first one. */
export function useActiveOrganisation() {
  const { data } = useSession();
  const stored = useSyncExternalStore(subscribeActiveOrganisation, getActiveOrganisationId, () => null);
  const orgs = data?.organisations ?? [];
  const active = orgs.find((o) => o.id === stored) ?? orgs[0] ?? null;
  useEffect(() => {
    // Persist the fallback so the API header matches what the UI shows.
    if (active && active.id !== stored) setActiveOrganisationId(active.id);
  }, [active, stored]);
  // Tenant queries wait until the stored id matches, so no request goes out with a stale header.
  return active && active.id === stored ? active : null;
}

export function useSwitchOrganisation() {
  const queryClient = useQueryClient();
  return useCallback(
    (id: string) => {
      setActiveOrganisationId(id);
      // Everything tenant-scoped must be refetched for the new organisation.
      queryClient.removeQueries({ predicate: (q) => q.queryKey[0] === "tenant" });
    },
    [queryClient],
  );
}

export function useCurrentOrganisation() {
  const active = useActiveOrganisation();
  return useQuery({
    queryKey: ["tenant", active?.id, "organisation"],
    queryFn: () => api.get<CurrentOrganisation>("/organisations/current"),
    enabled: Boolean(active),
    retry: (count, error) => !(error instanceof ApiRequestError && error.status < 500) && count < 2,
  });
}

export function usePermissions() {
  const { data } = useCurrentOrganisation();
  const set = new Set(data?.permissions ?? []);
  return { can: (p: Permission) => set.has(p), loaded: Boolean(data) };
}
