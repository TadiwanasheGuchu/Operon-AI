import { Link2 } from "lucide-react";
import Link from "next/link";

import { ProvenanceBadge } from "@/components/data-display/provenance-badge";
import { EmptyState } from "@/components/feedback/states";
import { Button } from "@/components/ui/button";
import { Panel, PanelHeader } from "@/components/ui/panel";
import type { Approval, Provenance } from "@/features/dashboard/contract";
import { formatCurrency, formatRelative } from "@/lib/format";

export function ApprovalsPanel({ approvals, provenance }: { approvals: Approval[]; provenance: Provenance }) {
  const sorted = [...approvals].sort((a, b) => a.requested_at.localeCompare(b.requested_at));
  return (
    <Panel aria-labelledby="approvals-title" id="approvals" className="scroll-mt-24">
      <PanelHeader
        id="approvals-title"
        title="Pending approvals"
        description="Oldest first. Requesters cannot approve their own requests."
        actions={
          <>
            {provenance === "live" ? (
              <Button variant="tertiary" size="sm" asChild>
                <Link href="/approvals">Open inbox</Link>
              </Button>
            ) : null}
            <ProvenanceBadge provenance={provenance} />
          </>
        }
      />
      {sorted.length === 0 ? (
        <EmptyState compact title="Nothing waiting for a decision" />
      ) : (
        <ul className="divide-y divide-line border-t border-line">
          {sorted.map((a) => (
            <li key={a.id} className="px-5 py-3">
              <div className="flex items-baseline justify-between gap-3">
                <p className="min-w-0 truncate text-[13px] font-medium text-ink" title={a.title}>
                  {provenance === "live" ? (
                    <Link href={`/workflows/${a.id}`} className="underline-offset-4 hover:underline">
                      {a.title}
                    </Link>
                  ) : (
                    a.title
                  )}
                </p>
                <p className="shrink-0 text-[13px] font-semibold text-ink tnum">
                  {a.amount !== null && a.currency ? formatCurrency(a.amount, a.currency) : "Value not known"}
                </p>
              </div>
              <div className="mt-0.5 flex flex-wrap items-center gap-x-2 text-xs text-ink-muted">
                <span className="font-mono text-[11px]">{a.ref}</span>
                <span aria-hidden>·</span>
                <span>{a.requester}</span>
                <span aria-hidden>·</span>
                <time dateTime={a.requested_at}>waiting {formatRelative(a.requested_at).replace(" ago", "")}</time>
              </div>
              <p className="mt-1 text-xs text-ink-secondary">{a.policy}</p>
              {a.related_insight_ref ? (
                <p className="mt-1 inline-flex items-center gap-1 text-xs text-ink-muted">
                  <Link2 className="size-3" aria-hidden /> Raised from {a.related_insight_ref}
                </p>
              ) : null}
            </li>
          ))}
        </ul>
      )}
    </Panel>
  );
}
