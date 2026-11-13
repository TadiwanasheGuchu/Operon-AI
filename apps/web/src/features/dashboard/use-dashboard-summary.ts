"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { useActiveOrganisation } from "@/features/session/use-session";
import { api } from "@/lib/api/client";

import { dashboardSummarySchema, layoutSettingsSchema, type Period } from "./contract";

export function useDashboardSummary(period: Period) {
  const org = useActiveOrganisation();
  return useQuery({
    queryKey: ["tenant", org?.id, "dashboard", period],
    queryFn: async () => dashboardSummarySchema.parse(await api.get(`/dashboard/summary?period=${period}`)),
    enabled: Boolean(org),
    staleTime: 60_000,
    refetchInterval: 5 * 60_000,
  });
}

export function useLayoutSettings() {
  const org = useActiveOrganisation();
  return useQuery({
    queryKey: ["tenant", org?.id, "dashboard-layout"],
    queryFn: async () => layoutSettingsSchema.parse(await api.get("/dashboard/layout")),
    enabled: Boolean(org),
  });
}

export function useSetLayout() {
  const queryClient = useQueryClient();
  const org = useActiveOrganisation();
  return useMutation({
    mutationFn: async (preset: string | null) =>
      layoutSettingsSchema.parse(await api.put("/dashboard/layout", { preset })),
    onSuccess: () =>
      Promise.all([
        queryClient.invalidateQueries({ queryKey: ["tenant", org?.id, "dashboard"] }),
        queryClient.invalidateQueries({ queryKey: ["tenant", org?.id, "dashboard-layout"] }),
      ]),
  });
}
