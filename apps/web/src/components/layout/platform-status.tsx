"use client";

import { usePlatformStatus } from "@/features/platform/use-platform-status";
import { cn } from "@/lib/cn";

/** Live API readiness from /api/v1/health/ready — real data in every environment. */
export function PlatformStatus({ collapsed }: { collapsed: boolean }) {
  const { data, isPending, isError } = usePlatformStatus();
  const state = isPending ? "checking" : isError || data?.status !== "ok" ? "down" : "up";
  const label =
    state === "checking" ? "Checking platform…" : state === "up" ? "Platform operational" : "Platform unavailable";
  const detail =
    state === "down" && data
      ? data.checks.filter((c) => c.status !== "ok").map((c) => c.name).join(", ") + " unavailable"
      : state === "up" && data
        ? `API ${data.version}`
        : state === "down"
          ? "API not reachable"
          : null;

  return (
    <div
      role="status"
      aria-live="polite"
      className={cn("flex items-center gap-2.5 text-xs", collapsed && "justify-center")}
      title={collapsed ? `${label}${detail ? ` — ${detail}` : ""}` : undefined}
    >
      <span
        aria-hidden
        className={cn(
          "inline-block size-2 shrink-0 rounded-full",
          state === "up" && "bg-success",
          state === "down" && "bg-danger",
          state === "checking" && "bg-ink-nav-muted",
        )}
      />
      <span className={cn("min-w-0", collapsed && "sr-only")}>
        <span className="block text-ink-nav">{label}</span>
        {detail ? <span className="block font-mono text-[11px] text-ink-nav-muted">{detail}</span> : null}
      </span>
    </div>
  );
}
