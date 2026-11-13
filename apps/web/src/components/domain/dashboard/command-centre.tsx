"use client";

import { ArrowDown, RefreshCw } from "lucide-react";
import { useState } from "react";

import { ProvenanceBadge } from "@/components/data-display/provenance-badge";
import { ErrorState } from "@/components/feedback/states";
import { Button } from "@/components/ui/button";
import { Panel } from "@/components/ui/panel";
import { Skeleton } from "@/components/ui/skeleton";
import { arrange, type Placement } from "@/features/dashboard/arrange";
import type { DashboardSummary, Period } from "@/features/dashboard/contract";
import { useDashboardSummary } from "@/features/dashboard/use-dashboard-summary";
import { ApiRequestError } from "@/lib/api/client";
import { cn } from "@/lib/cn";
import { formatRelative } from "@/lib/format";

import { ActivityFeed } from "./activity-feed";
import { ApprovalsPanel } from "./approvals-panel";
import { FillRateChart } from "./fill-rate-chart";
import { GettingStarted } from "./getting-started";
import { IncidentSeverity } from "./incident-severity";
import { IndicatorStrip } from "./indicator-strip";
import { InsightsPanel } from "./insights-panel";
import { IntegrationsStatus } from "./integrations-status";
import { InventoryRisk } from "./inventory-risk";
import { LayoutControl } from "./layout-control";
import { NotAvailable } from "./not-available";
import { PeriodControl } from "./period-control";
import { TeamPanel } from "./team-panel";
import { WorkflowsTable } from "./workflows-table";

function greeting(date: Date) {
  const h = date.getHours();
  return h < 12 ? "Good morning" : h < 18 ? "Good afternoon" : "Good evening";
}

/** Renders one ready section. Callers guarantee `state === "ready"`, so data is present. */
function SectionView({ placement, s, period }: { placement: Placement; s: DashboardSummary; period: Period }) {
  switch (placement.key) {
    case "getting_started":
      return <GettingStarted steps={s.getting_started.data ?? []} />;
    case "insights":
      return (
        <InsightsPanel
          insights={s.insights.data ?? []}
          openCount={s.indicators.find((i) => i.key === "open_insights")?.value ?? null}
          provenance={s.insights.provenance}
        />
      );
    case "approvals":
      return <ApprovalsPanel approvals={s.approvals.data ?? []} provenance={s.approvals.provenance} />;
    case "incidents":
      return s.incidents.data ? <IncidentSeverity counts={s.incidents.data} provenance={s.incidents.provenance} /> : null;
    case "fill_rate":
      return s.fill_rate.data ? <FillRateChart fillRate={s.fill_rate.data} period={period} provenance={s.fill_rate.provenance} /> : null;
    case "inventory_risk":
      return <InventoryRisk rows={s.inventory_risk.data ?? []} provenance={s.inventory_risk.provenance} />;
    case "workflows":
      return <WorkflowsTable workflows={s.workflows.data ?? []} provenance={s.workflows.provenance} />;
    case "integrations":
      return <IntegrationsStatus integrations={s.integrations.data ?? []} provenance={s.integrations.provenance} />;
    case "activity":
      return <ActivityFeed events={s.activity.data ?? []} provenance={s.activity.provenance} />;
    case "team":
      return s.team.data ? <TeamPanel team={s.team.data} provenance={s.team.provenance} /> : null;
  }
}

export function CommandCentre() {
  const [period, setPeriod] = useState<Period>("7d");
  const { data, error, isPending, isFetching, refetch, dataUpdatedAt } = useDashboardSummary(period);
  const arrangement = data ? arrange(data) : null;
  const hasExceptions = data?.insights.state === "ready" && (data.insights.data?.length ?? 0) > 0;

  return (
    <div className="mx-auto max-w-[1440px] px-4 pt-6 pb-12 md:px-6 lg:px-9 lg:pt-8">
      <div className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
        <div className="min-w-0">
          <p className="text-[13px] text-ink-muted">{data?.organisation.name ?? " "}</p>
          <h1 className="mt-1 font-display text-[30px] leading-9 font-medium tracking-[-0.01em] text-ink md:text-[34px] md:leading-10">
            {data ? `${greeting(new Date())}, ${data.viewer.name.split(" ")[0]}` : "Operations overview"}
          </h1>
          <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1.5 text-xs text-ink-muted">
            {data ? <ProvenanceBadge provenance={data.organisation.is_demo ? "demo" : "live"} /> : null}
            {data ? <span>{data.layout.name} view</span> : null}
            {dataUpdatedAt ? (
              <span className="inline-flex items-center gap-1">
                Refreshed {formatRelative(new Date(dataUpdatedAt).toISOString())}
                <button
                  type="button"
                  onClick={() => refetch()}
                  className="inline-flex size-6 items-center justify-center rounded-[6px] text-icon hover:bg-sunken hover:text-ink"
                  aria-label="Refresh overview"
                >
                  <RefreshCw className={isFetching ? "size-3.5 animate-spin" : "size-3.5"} aria-hidden />
                </button>
              </span>
            ) : null}
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <LayoutControl />
          <PeriodControl value={period} onChange={setPeriod} />
          {hasExceptions ? (
            <Button asChild>
              <a href="#exceptions">
                Review exceptions
                <ArrowDown aria-hidden />
              </a>
            </Button>
          ) : null}
        </div>
      </div>

      <div className="mt-6 space-y-5" aria-busy={isPending}>
        {isPending ? (
          <CommandCentreSkeleton />
        ) : error ? (
          <Panel>
            <ErrorState
              title="The overview couldn't be loaded"
              requestId={error instanceof ApiRequestError ? error.requestId : null}
              onRetry={() => refetch()}
            />
          </Panel>
        ) : (
          <>
            <IndicatorStrip indicators={data.indicators} period={period} />
            <div className="grid grid-flow-row-dense grid-cols-1 gap-5 xl:grid-cols-12">
              {arrangement!.panels.map((p) => (
                <div key={p.key} className={cn("min-w-0", p.size === "wide" ? "xl:col-span-8" : "xl:col-span-4")}>
                  <SectionView placement={p} s={data} period={period} />
                </div>
              ))}
              {arrangement!.unavailable.length ? (
                <div className="xl:col-span-12">
                  <NotAvailable items={arrangement!.unavailable} />
                </div>
              ) : null}
            </div>
          </>
        )}
      </div>
    </div>
  );
}

function CommandCentreSkeleton() {
  return (
    <div role="status" aria-label="Loading overview" className="space-y-5">
      <Panel className="grid grid-cols-2 gap-6 p-5 sm:grid-cols-3 xl:grid-cols-5">
        {Array.from({ length: 5 }, (_, i) => (
          <div key={i} className="space-y-2">
            <Skeleton className="h-3.5 w-24" />
            <Skeleton className="h-8 w-14" />
            <Skeleton className="h-3 w-28" />
          </div>
        ))}
      </Panel>
      <div className="grid gap-5 xl:grid-cols-12">
        <Panel className="space-y-3 p-5 xl:col-span-8">
          <Skeleton className="h-4 w-40" />
          <Skeleton className="h-24 w-full" />
        </Panel>
        <Panel className="space-y-3 p-5 xl:col-span-4">
          <Skeleton className="h-4 w-32" />
          <Skeleton className="h-12 w-full" />
        </Panel>
      </div>
    </div>
  );
}
