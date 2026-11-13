"use client";

import { Radar, Settings2 } from "lucide-react";
import Link from "next/link";
import { useState } from "react";

import { Pager } from "@/components/data-display/pager";
import { Table, TableScroll, Td, Th, Tr } from "@/components/data-display/table";
import { EmptyState, ErrorState, PermissionDenied } from "@/components/feedback/states";
import { useToast } from "@/components/feedback/toast";
import { PageContainer, PageHeader } from "@/components/layout/page-header";
import { SEVERITY, SeverityBadge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Select } from "@/components/ui/form";
import { Panel } from "@/components/ui/panel";
import { Segmented } from "@/components/ui/segmented";
import { Skeleton } from "@/components/ui/skeleton";
import type { Severity } from "@/features/dashboard/contract";
import {
  type DetectionRun,
  type InsightFilter,
  PAGE_SIZE,
  RULE_LABEL,
  useDetectionRuns,
  useInsightMutation,
  useInsights,
} from "@/features/intelligence/api";
import { useWorkspace } from "@/features/workspace/workspace-context";
import { api, errorMessage } from "@/lib/api/client";
import { formatRelative } from "@/lib/format";

import { InsightStatusBadge, LowConfidenceBadge } from "./status";

const SEVERITIES: Severity[] = ["critical", "high", "medium", "low"];

export function IntelligencePage() {
  const { workspace } = useWorkspace();
  const [filter, setFilter] = useState<InsightFilter>("active");
  const [severity, setSeverity] = useState<Severity | "">("");
  const [page, setPage] = useState(0);
  const list = useInsights(filter, severity, page);

  if (!workspace.can("insights.read")) {
    return (
      <PageContainer>
        <PermissionDenied permission="insights.read" />
      </PageContainer>
    );
  }
  const counts = list.data?.active_by_severity ?? {};
  return (
    <PageContainer>
      <PageHeader
        title="Intelligence"
        description="Problems Operon's rules found in your operational data. Every number is calculated by a documented rule and links back to the record it came from."
        actions={
          <>
            <Button variant="secondary" asChild>
              <Link href="/intelligence/settings">
                <Settings2 aria-hidden /> Detectors and AI
              </Link>
            </Button>
            {workspace.can("insights.manage") ? <RunButton /> : null}
          </>
        }
      />
      <LastRun />

      <div className="mt-5 flex flex-wrap items-center gap-3">
        <Segmented
          label="Insight status"
          value={filter}
          onChange={(v) => {
            setFilter(v);
            setPage(0);
          }}
          options={[
            { value: "active", label: "Active", count: SEVERITIES.reduce((n, s) => n + (counts[s] ?? 0), 0) },
            { value: "closed", label: "Closed" },
            { value: "all", label: "All" },
          ]}
        />
        <label className="sr-only" htmlFor="severity-filter">
          Severity
        </label>
        <Select
          id="severity-filter"
          className="h-9 w-44"
          value={severity}
          onChange={(e) => {
            setSeverity(e.target.value as Severity | "");
            setPage(0);
          }}
        >
          <option value="">All severities</option>
          {SEVERITIES.map((s) => (
            <option key={s} value={s}>
              {SEVERITY[s].label}
              {counts[s] ? ` (${counts[s]} active)` : ""}
            </option>
          ))}
        </Select>
      </div>

      <Panel className="mt-4" aria-label="Insights">
        {list.isPending ? (
          <div role="status" aria-label="Loading insights" className="space-y-3 p-5">
            <Skeleton className="h-10 w-full" />
            <Skeleton className="h-10 w-full" />
            <Skeleton className="h-10 w-full" />
          </div>
        ) : list.isError ? (
          <ErrorState compact onRetry={() => list.refetch()} />
        ) : list.data.items.length === 0 ? (
          <EmptyState
            compact
            icon={Radar}
            title={filter === "active" ? "No active insights" : "Nothing here"}
            description={
              filter === "active"
                ? "Detection runs after every sync and import. When a rule finds a problem, it appears here with its evidence."
                : "Resolved and dismissed insights appear here."
            }
          />
        ) : (
          <>
            <TableScroll>
              <Table>
                <thead>
                  <tr>
                    <Th>Severity</Th>
                    <Th>Insight</Th>
                    <Th>Status</Th>
                    <Th>Owner</Th>
                    <Th>Detected</Th>
                  </tr>
                </thead>
                <tbody>
                  {list.data.items.map((i) => (
                    <Tr key={i.id}>
                      <Td>
                        <SeverityBadge severity={i.severity} />
                      </Td>
                      <Td className="max-w-[520px] py-2.5">
                        <div className="flex flex-wrap items-center gap-2">
                          <span className="font-mono text-[11px] text-ink-muted">{i.reference}</span>
                          <span className="text-xs text-ink-muted">{RULE_LABEL[i.rule_id] ?? i.rule_id}</span>
                          {i.confidence === "low" ? <LowConfidenceBadge /> : null}
                        </div>
                        <Link href={`/intelligence/${i.id}`} className="mt-0.5 block font-medium underline-offset-4 hover:underline">
                          {i.title}
                        </Link>
                        <p className="truncate text-xs text-ink-muted">{i.summary}</p>
                      </Td>
                      <Td>
                        <InsightStatusBadge status={i.status} />
                        {i.incident_id ? (
                          <Link href={`/incidents/${i.incident_id}`} className="mt-1 block text-xs text-ink-secondary underline underline-offset-4">
                            Incident open
                          </Link>
                        ) : null}
                      </Td>
                      <Td className="text-ink-secondary">{i.owner?.full_name ?? "Unassigned"}</Td>
                      <Td className="whitespace-nowrap text-ink-secondary">
                        <time dateTime={i.detected_at}>{formatRelative(i.detected_at)}</time>
                      </Td>
                    </Tr>
                  ))}
                </tbody>
              </Table>
            </TableScroll>
            <Pager page={page} pageSize={PAGE_SIZE} total={list.data.total} onPage={setPage} />
          </>
        )}
      </Panel>
    </PageContainer>
  );
}

function RunButton() {
  const toast = useToast();
  const run = useInsightMutation(() => api.post<DetectionRun>("/intelligence/run"));
  return (
    <Button
      loading={run.isPending}
      onClick={() =>
        run.mutate(undefined, {
          onSuccess: (r) => toast({ tone: r.status === "succeeded" ? "success" : "danger", title: r.status === "succeeded" ? "Detection finished" : "Detection partly failed", description: describeRun(r) }),
          onError: (e) => toast({ tone: "danger", title: "Detection didn't run", description: errorMessage(e) }),
        })
      }
    >
      <Radar aria-hidden /> Run detection
    </Button>
  );
}

function describeRun(r: DetectionRun): string {
  let raised = 0;
  let updated = 0;
  let resolved = 0;
  for (const [rule, s] of Object.entries(r.stats)) {
    if (rule === "explanations") continue;
    raised += Number(s.raised ?? 0);
    updated += Number(s.updated ?? 0);
    resolved += Number(s.resolved ?? 0);
  }
  if (r.status === "failed") return "Some detectors failed; the others ran.";
  return `${raised} new, ${updated} updated, ${resolved} resolved.`;
}

const TRIGGER_LABEL: Record<DetectionRun["trigger"], string> = {
  sync: "after a sync",
  upload: "after an import",
  manual: "on request",
  schedule: "on schedule",
};

function LastRun() {
  const runs = useDetectionRuns();
  const last = runs.data?.[0];
  if (!last) return null;
  return (
    <p className="mt-3 text-xs text-ink-muted">
      Last checked <time dateTime={last.started_at}>{formatRelative(last.started_at)}</time> {TRIGGER_LABEL[last.trigger]} ·{" "}
      {describeRun(last)}
    </p>
  );
}
