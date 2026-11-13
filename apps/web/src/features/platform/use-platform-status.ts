"use client";

import { useQuery } from "@tanstack/react-query";
import { z } from "zod";


const readinessSchema = z.object({
  status: z.enum(["ok", "unavailable"]),
  version: z.string(),
  checks: z.array(z.object({ name: z.string(), status: z.enum(["ok", "unavailable"]) })),
});
export type Readiness = z.infer<typeof readinessSchema>;

/** Live readiness of the Operon API (GET /api/v1/health/ready). 503 still carries a body. */
async function fetchReadiness(): Promise<Readiness> {
  const response = await fetch("/api/v1/health/ready", { headers: { Accept: "application/json" } });
  const body: unknown = await response.json().catch(() => null);
  const parsed = readinessSchema.safeParse(body);
  if (!parsed.success) throw new Error("API unreachable");
  return parsed.data;
}

export function usePlatformStatus() {
  return useQuery({
    queryKey: ["platform", "readiness"],
    queryFn: fetchReadiness,
    refetchInterval: 30_000,
    retry: false,
  });
}

