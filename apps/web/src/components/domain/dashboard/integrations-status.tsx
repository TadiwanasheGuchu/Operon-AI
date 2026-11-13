import { ProvenanceBadge } from "@/components/data-display/provenance-badge";
import Link from "next/link";

import { StatusBadge } from "@/components/ui/badge";
import { Panel, PanelHeader } from "@/components/ui/panel";
import type { IntegrationStatus, Provenance } from "@/features/dashboard/contract";
import { formatRelative } from "@/lib/format";

export function IntegrationsStatus({ integrations, provenance }: { integrations: IntegrationStatus[]; provenance: Provenance }) {
  return (
    <Panel aria-labelledby="integrations-title" id="integrations" className="scroll-mt-24">
      <PanelHeader id="integrations-title" title="Integration status" actions={<ProvenanceBadge provenance={provenance} />} />
      <ul className="divide-y divide-line border-t border-line">
        {integrations.map((i) => (
          <li key={i.id} className="flex items-start gap-3 px-5 py-3">
            <div className="min-w-0 flex-1">
              <p className="text-[13px] font-medium text-ink">
                <Link href={`/integrations/${i.id}`} className="underline-offset-4 hover:underline">
                  {i.name}
                </Link>{" "}
                <span className="font-normal text-ink-muted">· {i.system}</span>
              </p>
              <p className="mt-0.5 text-xs text-ink-secondary">{i.detail}</p>
              <p className="mt-0.5 font-mono text-[11px] text-ink-muted">
                Last synchronised {i.last_sync_at ? formatRelative(i.last_sync_at) : "never"}
              </p>
            </div>
            <StatusBadge
              status={i.status === "degraded" ? "attention" : i.status === "disconnected" ? "attention" : i.status}
              label={i.status === "disconnected" ? "Needs attention" : undefined}
            />
          </li>
        ))}
      </ul>
    </Panel>
  );
}
