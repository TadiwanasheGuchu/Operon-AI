"use client";

import { Bot, Play } from "lucide-react";
import Link from "next/link";
import { useState } from "react";

import { Table, TableScroll, Td, Th, Tr } from "@/components/data-display/table";
import { EmptyState, ErrorState, PermissionDenied } from "@/components/feedback/states";
import { InlineAlert } from "@/components/feedback/inline-alert";
import { useToast } from "@/components/feedback/toast";
import { PageContainer, PageHeader } from "@/components/layout/page-header";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Field, Input, Select, Switch } from "@/components/ui/form";
import { Panel, PanelBody, PanelHeader } from "@/components/ui/panel";
import { Skeleton } from "@/components/ui/skeleton";
import { useMembers } from "@/features/admin/api";
import {
  type AgentConfig,
  type AgentParams,
  TOOL_LABEL,
  useAgentConfig,
  useAgentMutation,
  useRuns,
} from "@/features/agents/api";
import { useWorkspace } from "@/features/workspace/workspace-context";
import { api, ApiRequestError, errorMessage } from "@/lib/api/client";
import { formatDateTime, formatNumber, formatRelative } from "@/lib/format";

import { RunStatusBadge } from "./status";

export function AgentsPage() {
  const { workspace } = useWorkspace();
  const config = useAgentConfig();
  if (!workspace.can("agents.read")) {
    return (
      <PageContainer>
        <PermissionDenied permission="agents.read" />
      </PageContainer>
    );
  }
  return (
    <PageContainer>
      <PageHeader
        title="AI agents"
        description="Agents work through Operon's own tools, within limits you set, and only for a named member. Anything they draft still needs a person's approval."
        actions={config.data && workspace.can("agents.run") ? <RunButton config={config.data} /> : null}
      />
      {config.isPending ? (
        <Skeleton className="mt-6 h-96 w-full" />
      ) : config.isError ? (
        <ErrorState compact onRetry={() => config.refetch()} />
      ) : (
        <>
          {!config.data.availability.available ? (
            <InlineAlert className="mt-5" tone="info" title="Agents can't run right now">
              {config.data.availability.reason}
            </InlineAlert>
          ) : null}
          <div className="mt-6 grid grid-cols-1 gap-6 xl:grid-cols-12">
            <div className="min-w-0 xl:col-span-7">
              <AgentSettings key={config.data.current_version + (config.data.run_as_user_id ?? "")} config={config.data} canManage={workspace.can("agents.manage")} />
            </div>
            <div className="min-w-0 xl:col-span-5">
              <RunHistory />
            </div>
          </div>
        </>
      )}
    </PageContainer>
  );
}

function RunButton({ config }: { config: AgentConfig }) {
  const toast = useToast();
  const run = useAgentMutation(() => api.post("/agents/inventory-replenishment/runs"));
  const blocked = !config.availability.available
    ? config.availability.reason
    : !config.run_as_user_id
      ? "Choose who the agent acts for first."
      : !config.enabled
        ? "Turn the agent on (and save) to run it."
        : null;
  return (
    <div className="flex flex-col items-end gap-1">
      <Button
        loading={run.isPending}
        aria-disabled={blocked ? "true" : undefined}
        aria-describedby={blocked ? "run-blocked" : undefined}
        className={blocked ? "cursor-not-allowed bg-shallows text-ink-secondary hover:bg-shallows" : undefined}
        onClick={() =>
          !blocked &&
          run.mutate(undefined, {
            onSuccess: () => toast({ tone: "success", title: "Agent run started", description: "Results appear in the run history." }),
            onError: (e) => toast({ tone: "danger", title: "The run didn't start", description: errorMessage(e) }),
          })
        }
      >
        <Play aria-hidden /> Run now
      </Button>
      {blocked ? (
        <span id="run-blocked" className="max-w-xs text-right text-xs text-ink-muted">
          {blocked}
        </span>
      ) : null}
    </div>
  );
}

const LIMIT_LABEL: Record<keyof AgentParams["limits"], string> = {
  max_steps: "Model turns per run",
  max_tool_calls: "Tool calls per run",
  max_tokens: "Tokens per run",
  max_seconds: "Seconds per run",
};

function AgentSettings({ config, canManage }: { config: AgentConfig; canManage: boolean }) {
  const toast = useToast();
  const { workspace } = useWorkspace();
  const members = useMembers(canManage && workspace.can("members.read"));
  const [enabled, setEnabled] = useState(config.enabled);
  const [schedule, setSchedule] = useState(config.schedule);
  const [runAs, setRunAs] = useState(config.run_as_user_id ?? "");
  const [params, setParams] = useState<AgentParams>(config.params);
  const [tools, setTools] = useState<Record<string, boolean>>(Object.fromEntries(config.tools.map((t) => [t.name, t.enabled])));
  const save = useAgentMutation(() =>
    api.put<AgentConfig>("/agents/inventory-replenishment", {
      enabled,
      schedule,
      run_as_user_id: runAs || null,
      params,
      tools,
    }),
  );
  const disabled = !canManage;
  return (
    <form
      className="space-y-6"
      onSubmit={(e) => {
        e.preventDefault();
        save.mutate(undefined, {
          onSuccess: () => toast({ tone: "success", title: "Agent settings saved" }),
          onError: (err) => toast({ tone: "danger", title: "Not saved", description: errorMessage(err) }),
        });
      }}
    >
      <Panel flat aria-labelledby="agent-title">
        <PanelHeader
          id="agent-title"
          title={config.name}
          description="Reviews open stockout-risk insights and drafts purchase requests for approval, then writes a short summary."
          actions={
            <div className="flex items-center gap-2">
              <span id="agent-on" className="text-xs text-ink-muted">
                {enabled ? "On" : "Off"}
              </span>
              <Switch checked={enabled} onCheckedChange={setEnabled} disabled={disabled} aria-labelledby="agent-title agent-on" />
            </div>
          }
        />
        <PanelBody className="grid gap-4 sm:grid-cols-2">
          <Field label="Acts for" hint="Requests it drafts are raised in this person's name, so they can't approve them. It can never do more than they can.">
            {(p) => (
              <Select {...p} value={runAs} disabled={disabled || !members.data} onChange={(e) => setRunAs(e.target.value)}>
                <option value="">Nobody yet</option>
                {config.run_as_user_id && !members.data?.some((m) => m.user_id === config.run_as_user_id) ? (
                  <option value={config.run_as_user_id}>{config.run_as_name}</option>
                ) : null}
                {members.data?.map((m) => (
                  <option key={m.user_id} value={m.user_id}>
                    {m.full_name} ({m.role_name})
                  </option>
                ))}
              </Select>
            )}
          </Field>
          <Field label="Schedule" hint={config.next_run_at ? `Next run ${formatDateTime(config.next_run_at)}.` : "Daily runs start at 06:00 UTC."}>
            {(p) => (
              <Select {...p} value={schedule} disabled={disabled} onChange={(e) => setSchedule(e.target.value as AgentConfig["schedule"])}>
                <option value="off">Only when run by hand</option>
                <option value="daily">Daily</option>
              </Select>
            )}
          </Field>
          <Field label="Draft for insights of at least">
            {(p) => (
              <Select
                {...p}
                value={params.min_severity}
                disabled={disabled}
                onChange={(e) => setParams({ ...params, min_severity: e.target.value as AgentParams["min_severity"] })}
              >
                <option value="critical">Critical</option>
                <option value="high">High</option>
                <option value="medium">Medium</option>
              </Select>
            )}
          </Field>
          <Field label="Most requests per run">
            {(p) => (
              <Input {...p} type="number" min={1} max={20} value={params.max_drafts} disabled={disabled} onChange={(e) => setParams({ ...params, max_drafts: Number(e.target.value) })} />
            )}
          </Field>
          <Field
            className="sm:col-span-2"
            label="Extra guidance"
            hint="For example: “Prefer Brightline for gloves.” It can't override the agent's rules, and requests still need approval."
          >
            {(p) => (
              <textarea
                {...p}
                rows={3}
                maxLength={2000}
                value={params.guidance}
                disabled={disabled}
                onChange={(e) => setParams({ ...params, guidance: e.target.value })}
                className="w-full rounded-control border border-line-control bg-raised px-3 py-2 text-sm text-ink hover:border-ink-secondary focus-visible:border-primary disabled:bg-sunken"
              />
            )}
          </Field>
        </PanelBody>
      </Panel>

      <Panel flat aria-labelledby="tools-title">
        <PanelHeader id="tools-title" title="Tools it may use" description="An allowlist. The agent is never offered anything else, and there's no tool for approving, cancelling or deleting." />
        <ul className="divide-y divide-line border-t border-line">
          {config.tools.map((t) => (
            <li key={t.name} className="flex items-start justify-between gap-4 py-3">
              <div className="min-w-0">
                <p className="flex flex-wrap items-center gap-2 text-sm text-ink">
                  {TOOL_LABEL[t.name] ?? t.name}
                  {t.writes ? <Badge tone="warning">Creates records</Badge> : <Badge>Read only</Badge>}
                </p>
                <p className="mt-0.5 text-xs text-ink-muted">
                  {t.description} <span className="font-mono">Needs {t.permission}.</span>
                </p>
                {t.run_as_permitted === false && tools[t.name] ? (
                  <p className="mt-1 text-xs text-warning">The member it acts for doesn&apos;t have {t.permission}, so it won&apos;t be offered.</p>
                ) : null}
              </div>
              <Switch
                checked={tools[t.name] ?? false}
                onCheckedChange={(v) => setTools({ ...tools, [t.name]: v })}
                disabled={disabled}
                aria-label={`Allow: ${TOOL_LABEL[t.name] ?? t.name}`}
              />
            </li>
          ))}
        </ul>
      </Panel>

      <Panel flat aria-labelledby="limits-title">
        <PanelHeader id="limits-title" title="Limits" description="A run stops when it reaches any of these. Every run also counts towards the monthly AI token budget." />
        <PanelBody className="grid gap-4 sm:grid-cols-2">
          {(Object.keys(LIMIT_LABEL) as (keyof AgentParams["limits"])[]).map((k) => (
            <Field key={k} label={LIMIT_LABEL[k]}>
              {(p) => (
                <Input
                  {...p}
                  type="number"
                  min={1}
                  value={params.limits[k]}
                  disabled={disabled}
                  onChange={(e) => setParams({ ...params, limits: { ...params.limits, [k]: Number(e.target.value) } })}
                />
              )}
            </Field>
          ))}
        </PanelBody>
      </Panel>

      {canManage ? (
        <div className="flex items-center gap-3">
          <Button type="submit" loading={save.isPending}>
            Save settings
          </Button>
          <span className="text-xs text-ink-muted">Version {config.current_version}. Changing instructions or limits creates a new version.</span>
        </div>
      ) : (
        <p className="text-xs text-ink-muted">You can view these settings. Changing them requires agents.manage.</p>
      )}
      {save.error instanceof ApiRequestError && save.error.code === "invalid_params" ? (
        <InlineAlert tone="danger" title="Some settings are out of range">
          {((save.error.details as { errors?: { field: string; message: string }[] }).errors ?? []).map((x) => `${x.field}: ${x.message}`).join("; ")}
        </InlineAlert>
      ) : null}
    </form>
  );
}

function RunHistory() {
  const runs = useRuns();
  return (
    <Panel aria-labelledby="runs-title">
      <PanelHeader id="runs-title" title="Run history" description="Every run keeps a complete log." />
      {runs.isPending ? (
        <div className="p-5">
          <Skeleton className="h-24 w-full" />
        </div>
      ) : runs.isError ? (
        <ErrorState compact onRetry={() => runs.refetch()} />
      ) : runs.data.length === 0 ? (
        <EmptyState compact icon={Bot} title="No runs yet" description="Run it by hand, or turn on the daily schedule." />
      ) : (
        <TableScroll className="border-t border-line">
          <Table>
            <thead>
              <tr>
                <Th>Run</Th>
                <Th>Status</Th>
                <Th numeric>Tokens</Th>
              </tr>
            </thead>
            <tbody>
              {runs.data.map((r) => (
                <Tr key={r.id}>
                  <Td className="py-2.5">
                    <Link href={`/agents/runs/${r.id}`} className="font-medium underline-offset-4 hover:underline">
                      <time dateTime={r.started_at}>{formatRelative(r.started_at)}</time>
                    </Link>
                    <p className="text-xs text-ink-muted">
                      {r.trigger === "schedule" ? "Scheduled" : `By ${r.triggered_by_name ?? "a member"}`} · {r.tool_calls} tool calls
                    </p>
                  </Td>
                  <Td>
                    <RunStatusBadge status={r.status} />
                  </Td>
                  <Td numeric className="text-ink-secondary">
                    {formatNumber(r.input_tokens + r.output_tokens)}
                  </Td>
                </Tr>
              ))}
            </tbody>
          </Table>
        </TableScroll>
      )}
    </Panel>
  );
}
