import Link from "next/link";

import { ProvenanceBadge } from "@/components/data-display/provenance-badge";
import { SEVERITY } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Panel, PanelBody, PanelHeader } from "@/components/ui/panel";
import type { IncidentCounts, Provenance, Severity } from "@/features/dashboard/contract";
import { cn } from "@/lib/cn";

const ORDER: Severity[] = ["critical", "high", "medium", "low"];
const ICON: Record<Severity, string> = {
  critical: "text-danger",
  high: "text-warning",
  medium: "text-info",
  low: "text-ink-muted",
};
const FILL: Record<Severity, string> = {
  critical: "bg-danger",
  high: "bg-warning",
  medium: "bg-info",
  low: "bg-icon",
};

export function IncidentSeverity({ counts, provenance }: { counts: IncidentCounts; provenance: Provenance }) {
  const total = ORDER.reduce((s, k) => s + (counts[k] ?? 0), 0);
  return (
    <Panel aria-labelledby="incidents-title" id="incidents" className="scroll-mt-24">
      <PanelHeader
        id="incidents-title"
        title="Active incidents"
        description={`${total} open, by severity`}
        actions={
          <>
            {provenance === "live" ? (
              <Button variant="tertiary" size="sm" asChild>
                <Link href="/incidents">View all</Link>
              </Button>
            ) : null}
            <ProvenanceBadge provenance={provenance} />
          </>
        }
      />
      <PanelBody>
        {total > 0 ? (
          <div className="mb-3 flex h-2 gap-0.5 overflow-hidden" aria-hidden>
            {ORDER.filter((k) => counts[k]).map((k) => (
              <div key={k} className={cn("h-2 rounded-full", FILL[k])} style={{ flexGrow: counts[k] }} />
            ))}
          </div>
        ) : null}
        <ul className="grid grid-cols-2 gap-x-4 gap-y-2">
          {ORDER.map((k) => {
            const s = SEVERITY[k];
            const Icon = s.icon;
            return (
              <li key={k} className="flex items-center gap-2 text-[13px]">
                <Icon className={cn("size-3.5", ICON[k])} aria-hidden />
                <span className="flex-1 text-ink-secondary">{s.label}</span>
                <span className="font-medium text-ink tnum">{counts[k] ?? 0}</span>
              </li>
            );
          })}
        </ul>
      </PanelBody>
    </Panel>
  );
}
