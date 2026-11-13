"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { useActiveOrganisation } from "@/features/session/use-session";
import { api } from "@/lib/api/client";

export interface Notification {
  id: string;
  kind: "member" | "security" | "insight" | "approval" | "incident" | "integration" | "workflow";
  title: string;
  body: string;
  link: string | null;
  created_at: string;
  read_at: string | null;
}

export function useNotifications() {
  const org = useActiveOrganisation();
  return useQuery({
    queryKey: ["tenant", org?.id, "notifications"],
    queryFn: () => api.get<{ items: Notification[]; unread_count: number }>("/notifications?limit=20"),
    enabled: Boolean(org),
    refetchInterval: 60_000,
  });
}

export function useMarkNotifications() {
  const queryClient = useQueryClient();
  const org = useActiveOrganisation();
  const refresh = () => queryClient.invalidateQueries({ queryKey: ["tenant", org?.id, "notifications"] });
  return {
    markRead: useMutation({ mutationFn: (id: string) => api.post(`/notifications/${id}/read`), onSuccess: refresh }),
    markAllRead: useMutation({ mutationFn: () => api.post("/notifications/read-all"), onSuccess: refresh }),
  };
}
