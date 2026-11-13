"use client";

import { ChevronDown, FileSearch } from "lucide-react";
import Link from "next/link";
import { useId, useState } from "react";

import { Table, TableScroll, Td, Th, Tr } from "@/components/data-display/table";
import { ProvenanceBadge } from "@/components/data-display/provenance-badge";
import { EmptyState } from "@/components/feedback/states";
import { Badge, SeverityBadge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Panel, PanelHeader } from "@/components/ui/panel";
import type { Insight, Provenance } from "@/features/dashboard/contract";
import { formatRelative } from "@/lib/format";
import { cn } from "@/lib/cn";

const SEVERITY_ORDER = { critical: 0, high: 1, medium: 2, low: 3 } as const;

export function InsightsPanel({
  insights,
  openCount,
  provenance,
}: {
  insights: Insight[];
  openCount: number | null;
  provenance: Provenance;
}) {
  const sorted = [...insights].sort((a, b) => SEVERITY_ORDER[a.severity] - SEVERITY_ORDER[b.severity]);
  return (
    <Panel aria-labelledby="exceptions-title" id="exceptions" className="scroll-mt-24">
      <PanelHeader
        id="exceptions-title"
        title="Priority exceptions"
        description={`Highest-severity insights first · ${sorted.length}${openCount ? ` of ${openCount}` : ""} open shown`}
        actions={
          <>
            {provenance === "live" ? (
              <Button variant="tertiary" size="sm" asChild>
                <Link href="/intelligence">View all</Link>
              </Button>
            ) : null}
            <ProvenanceBadge provenance={provenance} />
          </>
        }
      />
      {sorted.length === 0 ? (
        <EmptyState
          compact
          title="No open exceptions"
          description="Detection runs after each integration sync. New insights will appear here."
        />
      ) : (
        <ol className="divide-y divide-line border-t border-line">
          {sorted.map((insight, index) => (
            <li key={insight.id}>
              <InsightRow insight={insight} defaultOpen={index === 0} live={provenance === "live"} />
            </li>
          ))}
        </ol>
      )}
    </Panel>
  );
}

function InsightRow({ insight, defaultOpen, live }: { insight: Insight; defaultOpen: boolean; live: boolean }) {
  const [open, setOpen] = useState(defaultOpen);
  const detailId = useId();
  return (
    <article className="px-5 py-4" aria-labelledby={`${detailId}-title`}>
      <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
        <SeverityBadge severity={insight.severity} />
        <span className="font-mono text-[11px] text-ink-muted">{insight.ref}</span>
        {insight.status === "acknowledged" ? <Badge>Acknowledged</Badge> : null}
        <span className="ml-auto text-xs text-ink-muted">
          <time dateTime={insight.detected_at}>Detected {formatRelative(insight.detected_at)}</time>
        </span>
      </div>
      <h3 id={`${detailId}-title`} className="mt-2 text-[15px] leading-6 font-semibold text-ink">
        {/* Demo insights are illustrative and have no detail page. */}
        {live ? (
          <Link href={`/intelligence/${insight.id}`} className="underline-offset-4 hover:underline">
            {insight.title}
          </Link>
        ) : (
          insight.title
        )}
      </h3>
      <p className="mt-0.5 text-[13px] text-ink-secondary">{insight.summary}</p>

      <div className="mt-3 rounded-[10px] border border-line bg-canvas px-3.5 py-3">
        <p className="text-[11px] font-medium tracking-[0.06em] text-ink-muted uppercase">Recommended action</p>
        <p className="mt-1 text-[13px] text-ink">{insight.recommended_action}</p>
      </div>

      <div className="mt-3 flex flex-wrap items-center gap-x-3 gap-y-2">
        <Button
          variant="secondary"
          size="sm"
          aria-expanded={open}
          aria-controls={detailId}
          onClick={() => setOpen((o) => !o)}
        >
          <FileSearch aria-hidden />
          {open ? "Hide evidence" : "View evidence"}
          <ChevronDown
            aria-hidden
            className={cn("transition-transform transition-standard", open && "rotate-180")}
          />
        </Button>
        <span className="text-xs text-ink-muted">
          Source {insight.source_system} · Owner {insight.owner ?? "unassigned"}
        </span>
      </div>

      <div id={detailId} hidden={!open} className="mt-4 space-y-4">
        <section aria-label="Why it matters">
          <h4 className="text-xs font-semibold text-ink">Why it matters</h4>
          <p className="mt-1 text-[13px] text-ink-secondary">{insight.why_it_matters}</p>
        </section>

        <section aria-label="Evidence" className="-mx-5">
          <h4 className="px-5 text-xs font-semibold text-ink">Evidence</h4>
          <TableScroll className="mt-1.5">
            <Table>
              <thead>
                <tr>
                  <Th>Measure</Th>
                  <Th numeric>Value</Th>
                  <Th>Source or calculation</Th>
                </tr>
              </thead>
              <tbody>
                {insight.evidence.map((e, n) => (
                  <Tr key={`${n}-${e.label}`}>
                    <Td className="text-ink-secondary">{e.label}</Td>
                    <Td numeric className="font-medium whitespace-nowrap">
                      {e.value}
                    </Td>
                    <Td className="font-mono text-[11px] text-ink-muted">{e.source}</Td>
                  </Tr>
                ))}
              </tbody>
            </Table>
          </TableScroll>
        </section>

        <div className="grid gap-4 sm:grid-cols-2">
          <section aria-label="Assumptions">
            <h4 className="text-xs font-semibold text-ink">Assumptions</h4>
            <ul className="mt-1 list-disc space-y-1 pl-4 text-[13px] text-ink-secondary marker:text-icon">
              {insight.assumptions.map((a) => (
                <li key={a}>{a}</li>
              ))}
            </ul>
          </section>
          <section aria-label="Limitations">
            <h4 className="text-xs font-semibold text-ink">Limitations</h4>
            <ul className="mt-1 list-disc space-y-1 pl-4 text-[13px] text-ink-secondary marker:text-icon">
              {insight.limitations.map((l) => (
                <li key={l}>{l}</li>
              ))}
            </ul>
          </section>
        </div>

        <p className="border-t border-line pt-3 font-mono text-[11px] text-ink-muted">
          Detected by rule {insight.rule_id} v{insight.rule_version} ·{" "}
          {insight.explanation_generated_by === "model"
            ? `Explanation by ${insight.explanation_model}, checked against evidence`
            : "Explanation from template (no model used)"}
        </p>

        <div className="flex flex-wrap items-center gap-3">
          {live ? (
            <Button size="sm" asChild>
              <Link href={`/intelligence/${insight.id}`}>Review and act</Link>
            </Button>
          ) : (
            <>
              <Button size="sm" aria-disabled="true" className="cursor-not-allowed bg-shallows text-ink-secondary hover:bg-shallows" aria-describedby={`${detailId}-unavailable`}>
                Create purchase request
              </Button>
              <span id={`${detailId}-unavailable`} className="text-xs text-ink-muted">
                Sample data: actions are switched off in demo organisations.
              </span>
            </>
          )}
        </div>
      </div>
    </article>
  );
}
