"use client";

import { ArrowLeft, Ban, Bot, CircleAlert, Flag, Gauge, Wrench } from "lucide-react";
import Link from "next/link";

import { ErrorState } from "@/components/feedback/states";
import { PageContainer } from "@/components/layout/page-header";
import { Panel, PanelBody, PanelHeader } from "@/components/ui/panel";
import { Skeleton } from "@/components/ui/skeleton";
import { type RunDetail, type Step, TOOL_LABEL, useRun } from "@/features/agents/api";
import { ApiRequestError } from "@/lib/api/client";
import { formatDateTime, formatNumber } from "@/lib/format";

import { RunStatusBadge } from "./status";

export function RunPage({ id }: { id: string }) {
  const run = useRun(id);
  if (run.isPending) {
    return (
      <PageContainer>
        <div role="status" aria-label="Loading run" className="space-y-4">
          <Skeleton className="h-9 w-96 max-w-full" />
          <Skeleton className="h-64 w-full" />
        </div>
      </PageContainer>
    );
  }
  if (run.isError) {
    const notFound = run.error instanceof ApiRequestError && run.error.status === 404;
    return (
      <PageContainer>
        <ErrorState title={notFound ? "This run doesn't exist" : "The run couldn't be loaded"} onRetry={notFound ? undefined : () => run.refetch()} />
      </PageContainer>
    );
  }
  const r = run.data;
  return (
    <PageContainer>
      <Link href={r.kind === "agent" ? "/agents" : "/overview"} className="inline-flex items-center gap-1 text-[13px] text-ink-secondary hover:text-ink">
        <ArrowLeft className="size-4" aria-hidden /> {r.kind === "agent" ? "AI agents" : "Back"}
      </Link>
      <div className="mt-3 flex flex-wrap items-center gap-2">
        <RunStatusBadge status={r.status} />
        <span className="font-mono text-[11px] text-ink-muted">
          {r.kind === "agent" ? `Agent v${r.agent_version}` : "Assistant answer"} · {r.prompt_version}
        </span>
      </div>
      <h1 className="mt-2 font-display text-[28px] leading-9 font-medium text-ink">
        {r.kind === "agent" ? "Agent run" : "How this answer was produced"}
      </h1>
      <p className="mt-1.5 text-xs text-ink-muted">
        Started <time dateTime={r.started_at}>{formatDateTime(r.started_at)}</time>
        {r.trigger === "schedule" ? " on schedule" : r.triggered_by_name ? ` by ${r.triggered_by_name}` : ""}
        {r.stop_reason && r.status !== "succeeded" ? ` · stopped: ${r.stop_reason.replaceAll("_", " ")}` : ""}
      </p>
      <div className="mt-6 grid grid-cols-1 gap-6 xl:grid-cols-12">
        <div className="min-w-0 space-y-6 xl:col-span-8">
          {r.summary ? (
            <Panel flat aria-labelledby="summary-title">
              <PanelHeader id="summary-title" title={r.kind === "agent" ? "Summary" : "Answer"} />
              <PanelBody>
                <p className="text-sm leading-6 whitespace-pre-wrap text-ink">{r.summary}</p>
              </PanelBody>
            </Panel>
          ) : null}
          <Panel flat aria-labelledby="log-title">
            <PanelHeader id="log-title" title="Step log" description="Every model turn and tool call, in order. Entries can't be edited." />
            <ol className="space-y-3">
              {r.log.map((s) => (
                <StepView key={s.position} step={s} />
              ))}
            </ol>
          </Panel>
        </div>
        <div className="min-w-0 xl:col-span-4">
          <Facts run={r} />
        </div>
      </div>
    </PageContainer>
  );
}

const STEP: Record<Step["kind"], { label: string; icon: typeof Bot; tone: string }> = {
  model_turn: { label: "Model", icon: Bot, tone: "text-ink-secondary" },
  tool_call: { label: "Tool", icon: Wrench, tone: "text-primary" },
  tool_denied: { label: "Denied", icon: Ban, tone: "text-danger" },
  tool_error: { label: "Tool error", icon: CircleAlert, tone: "text-warning" },
  limit: { label: "Limit", icon: Gauge, tone: "text-warning" },
  refused: { label: "Declined", icon: Ban, tone: "text-ink-secondary" },
  final: { label: "Finished", icon: Flag, tone: "text-success" },
  error: { label: "Error", icon: CircleAlert, tone: "text-danger" },
};

function StepView({ step: s }: { step: Step }) {
  const meta = STEP[s.kind];
  const Icon = meta.icon;
  const calls = (s.output?.tool_calls as { name: string }[] | undefined) ?? [];
  return (
    <li className="border-l-2 border-line pl-3">
      <p className="flex flex-wrap items-center gap-2 text-[13px]">
        <span className={`inline-flex items-center gap-1 font-medium ${meta.tone}`}>
          <Icon className="size-3.5" aria-hidden /> {meta.label}
        </span>
        {s.tool_name ? <span className="text-ink">{TOOL_LABEL[s.tool_name] ?? s.tool_name}</span> : null}
        {s.kind === "model_turn" && calls.length ? (
          <span className="text-ink-secondary">asked for {calls.map((c) => TOOL_LABEL[c.name] ?? c.name).join(", ")}</span>
        ) : null}
        <span className="text-xs text-ink-muted">
          {s.input_tokens || s.output_tokens ? `${formatNumber(s.input_tokens + s.output_tokens)} tokens · ` : ""}
          {s.latency_ms ? `${formatNumber(s.latency_ms)} ms` : ""}
        </span>
      </p>
      {s.message ? <p className="mt-1 text-[13px] whitespace-pre-wrap text-ink-secondary">{s.message}</p> : null}
      {s.input || (s.kind === "tool_call" && s.output) ? (
        <details className="mt-1">
          <summary className="cursor-pointer text-xs text-ink-muted hover:text-ink">Input and output</summary>
          <pre className="mt-1 max-h-72 overflow-auto rounded-[8px] bg-sunken p-3 font-mono text-[11px] leading-4 whitespace-pre-wrap text-ink">
            {JSON.stringify({ input: s.input, output: s.kind === "tool_call" ? s.output : undefined }, null, 2)}
          </pre>
        </details>
      ) : null}
    </li>
  );
}

function Facts({ run: r }: { run: RunDetail }) {
  const rows: [string, string][] = [
    ["Model", `${r.model} (${r.provider})`],
    ["Model turns", String(r.steps)],
    ["Tool calls", String(r.tool_calls)],
    ["Tokens", `${formatNumber(r.input_tokens)} in · ${formatNumber(r.output_tokens)} out`],
    ["Finished", r.finished_at ? formatDateTime(r.finished_at) : "Still running"],
  ];
  return (
    <Panel aria-labelledby="facts-title">
      <PanelHeader id="facts-title" title="Run details" />
      <PanelBody className="space-y-4">
        <dl className="grid grid-cols-[minmax(0,2fr)_minmax(0,3fr)] gap-x-4 gap-y-2 text-sm">
          {rows.map(([k, v]) => (
            <div key={k} className="contents">
              <dt className="text-ink-muted">{k}</dt>
              <dd className="break-words text-ink">{v}</dd>
            </div>
          ))}
        </dl>
        <div>
          <h3 className="text-xs font-semibold text-ink">Tools offered</h3>
          <ul className="mt-1 space-y-0.5 text-[13px] text-ink-secondary">
            {r.tools_offered.map((t) => (
              <li key={t}>{TOOL_LABEL[t] ?? t}</li>
            ))}
          </ul>
        </div>
        {r.error ? <p className="text-xs text-danger">{r.error}</p> : null}
      </PanelBody>
    </Panel>
  );
}
