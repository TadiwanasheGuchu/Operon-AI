"use client";

import { ArrowLeft, Clock, Radar } from "lucide-react";
import Link from "next/link";
import { useState } from "react";

import { ErrorState, PermissionDenied } from "@/components/feedback/states";
import { InlineAlert } from "@/components/feedback/inline-alert";
import { useToast } from "@/components/feedback/toast";
import { PageContainer } from "@/components/layout/page-header";
import { SEVERITY, SeverityBadge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Field, Select } from "@/components/ui/form";
import { Panel, PanelBody, PanelHeader } from "@/components/ui/panel";
import { Skeleton } from "@/components/ui/skeleton";
import { useMembers } from "@/features/admin/api";
import type { Severity } from "@/features/dashboard/contract";
import {
  type IncidentDetail,
  type IncidentEvent,
  type IncidentStatus,
  INCIDENT_STATUS_LABEL,
  RESPONSE_TARGET_LABEL,
  useIncident,
  useIncidentMutation,
} from "@/features/incidents/api";
import { useWorkspace } from "@/features/workspace/workspace-context";
import { api, ApiRequestError, errorMessage } from "@/lib/api/client";
import { formatDateTime } from "@/lib/format";

import { ReasonDialog } from "../intelligence/reason-dialog";
import { IncidentStatusBadge } from "./status";

export function IncidentPage({ id }: { id: string }) {
  const { workspace } = useWorkspace();
  const incident = useIncident(id);
  if (!workspace.can("incidents.read")) {
    return (
      <PageContainer>
        <PermissionDenied permission="incidents.read" />
      </PageContainer>
    );
  }
  if (incident.isPending) {
    return (
      <PageContainer>
        <div role="status" aria-label="Loading incident" className="space-y-4">
          <Skeleton className="h-9 w-96 max-w-full" />
          <Skeleton className="h-48 w-full" />
        </div>
      </PageContainer>
    );
  }
  if (incident.isError) {
    const notFound = incident.error instanceof ApiRequestError && incident.error.status === 404;
    return (
      <PageContainer>
        <ErrorState
          title={notFound ? "This incident doesn't exist" : "The incident couldn't be loaded"}
          onRetry={notFound ? undefined : () => incident.refetch()}
        />
      </PageContainer>
    );
  }
  const i = incident.data;
  return (
    <PageContainer>
      <Link href="/incidents" className="inline-flex items-center gap-1 text-[13px] text-ink-secondary hover:text-ink">
        <ArrowLeft className="size-4" aria-hidden /> Incidents
      </Link>
      <Header incident={i} />
      <ResponseBanner incident={i} />
      <div className="mt-6 grid grid-cols-1 gap-5 xl:grid-cols-12">
        <div className="min-w-0 space-y-5 xl:col-span-8">
          {i.description ? (
            <Panel flat aria-labelledby="description-title">
              <PanelHeader id="description-title" title="Description" />
              <PanelBody>
                <p className="text-sm whitespace-pre-wrap text-ink">{i.description}</p>
              </PanelBody>
            </Panel>
          ) : null}
          {i.resolution ? (
            <Panel flat aria-labelledby="resolution-title">
              <PanelHeader id="resolution-title" title="Resolution" />
              <PanelBody>
                <p className="text-sm whitespace-pre-wrap text-ink">{i.resolution}</p>
              </PanelBody>
            </Panel>
          ) : null}
          <TimelinePanel incident={i} />
        </div>
        <div className="min-w-0 space-y-5 xl:col-span-4">
          <DetailsPanel incident={i} />
          {i.insight ? (
            <Panel aria-labelledby="insight-title">
              <PanelHeader id="insight-title" title="Raised from" />
              <PanelBody>
                <Link href={`/intelligence/${i.insight.id}`} className="group block">
                  <span className="inline-flex items-center gap-1.5 font-mono text-[11px] text-ink-muted">
                    <Radar className="size-3.5" aria-hidden /> {i.insight.reference}
                  </span>
                  <span className="mt-0.5 block text-sm font-medium text-ink underline-offset-4 group-hover:underline">
                    {i.insight.title}
                  </span>
                  <span className="mt-0.5 block text-xs text-ink-muted">Insight is {i.insight.status}</span>
                </Link>
              </PanelBody>
            </Panel>
          ) : null}
        </div>
      </div>
    </PageContainer>
  );
}

const ACTION: Record<IncidentStatus, string> = {
  open: "Reopen",
  investigating: "Start investigating",
  resolved: "Resolve",
};

function Header({ incident: i }: { incident: IncidentDetail }) {
  const { workspace } = useWorkspace();
  const toast = useToast();
  const [resolving, setResolving] = useState(false);
  const update = useIncidentMutation((body: Record<string, unknown>) => api.patch(`/incidents/${i.id}`, body));
  const canManage = workspace.can("incidents.manage");
  const go = (status: IncidentStatus, resolution?: string) =>
    update.mutateAsync(
      { status, resolution },
      {
        onSuccess: () => toast({ tone: "success", title: `${i.reference}: ${INCIDENT_STATUS_LABEL[status].toLowerCase()}` }),
        onError: (e) => toast({ tone: "danger", title: "Not updated", description: errorMessage(e) }),
      },
    );
  return (
    <div className="mt-3">
      <div className="flex flex-wrap items-center gap-2">
        <SeverityBadge severity={i.severity} />
        <IncidentStatusBadge status={i.status} />
        <span className="font-mono text-[11px] text-ink-muted">{i.reference}</span>
      </div>
      <div className="mt-2 flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
        <div className="min-w-0">
          <h1 className="font-display text-[28px] leading-9 font-medium text-ink">{i.title}</h1>
          <p className="mt-1.5 text-xs text-ink-muted">
            Opened <time dateTime={i.created_at}>{formatDateTime(i.created_at)}</time>
            {i.reported_by ? ` by ${i.reported_by.full_name}` : ""}
          </p>
        </div>
        {canManage ? (
          <div className="flex flex-wrap gap-2">
            {i.allowed_transitions.map((t) => (
              <Button
                key={t}
                variant={t === "investigating" && i.status === "open" ? "primary" : "secondary"}
                loading={update.isPending && update.variables?.status === t}
                onClick={() => (t === "resolved" ? setResolving(true) : go(t))}
              >
                {ACTION[t]}
              </Button>
            ))}
          </div>
        ) : null}
      </div>
      <ReasonDialog
        open={resolving}
        onOpenChange={setResolving}
        title={`Resolve ${i.reference}`}
        description="Record what was done, so the next person facing this problem can learn from it."
        label="Resolution"
        required
        confirmLabel="Resolve"
        onSubmit={(r) => go("resolved", r)}
      />
    </div>
  );
}

function ResponseBanner({ incident: i }: { incident: IncidentDetail }) {
  if (i.status !== "open") return null;
  return i.response_overdue ? (
    <InlineAlert className="mt-5" tone="danger" title="Response overdue">
      Nobody has started investigating. Managers have been notified{i.escalation_level > 1 ? ` ${i.escalation_level} times` : ""}.
      Start investigating to stop further escalation.
    </InlineAlert>
  ) : (
    <InlineAlert className="mt-5" tone="info" title={`Start investigating by ${formatDateTime(i.response_due_at)}`}>
      The response target for {SEVERITY[i.severity].label.toLowerCase()} incidents is {RESPONSE_TARGET_LABEL[i.severity]}. After that,
      it escalates to managers.
    </InlineAlert>
  );
}

function DetailsPanel({ incident: i }: { incident: IncidentDetail }) {
  const { workspace } = useWorkspace();
  const toast = useToast();
  const canManage = workspace.can("incidents.manage");
  const members = useMembers(canManage && workspace.can("members.read"));
  const update = useIncidentMutation((body: Record<string, unknown>) => api.patch(`/incidents/${i.id}`, body));
  const save = (body: Record<string, unknown>, title: string) =>
    update.mutate(body, {
      onSuccess: () => toast({ tone: "success", title }),
      onError: (e) => toast({ tone: "danger", title: "Not updated", description: errorMessage(e) }),
    });
  return (
    <Panel aria-labelledby="details-title">
      <PanelHeader id="details-title" title="Details" />
      <PanelBody className="space-y-4">
        {canManage ? (
          <>
            <Field label="Assignee">
              {(p) => (
                <Select
                  {...p}
                  value={i.assignee?.user_id ?? ""}
                  disabled={!members.data || update.isPending}
                  onChange={(e) => save({ assignee_user_id: e.target.value || null }, "Assignee updated")}
                >
                  <option value="">Unassigned</option>
                  {/* Keep the current assignee visible even if the member list isn't readable. */}
                  {i.assignee && !members.data?.some((m) => m.user_id === i.assignee?.user_id) ? (
                    <option value={i.assignee.user_id}>{i.assignee.full_name}</option>
                  ) : null}
                  {members.data?.map((m) => (
                    <option key={m.user_id} value={m.user_id}>
                      {m.full_name}
                    </option>
                  ))}
                </Select>
              )}
            </Field>
            <Field label="Severity" hint={i.status === "open" ? "Changing it resets the response target." : undefined}>
              {(p) => (
                <Select
                  {...p}
                  value={i.severity}
                  disabled={update.isPending}
                  onChange={(e) => save({ severity: e.target.value as Severity }, "Severity updated")}
                >
                  {(["critical", "high", "medium", "low"] as const).map((s) => (
                    <option key={s} value={s}>
                      {SEVERITY[s].label}
                    </option>
                  ))}
                </Select>
              )}
            </Field>
          </>
        ) : (
          <dl className="grid grid-cols-2 gap-y-2 text-sm">
            <dt className="text-ink-muted">Assignee</dt>
            <dd className="text-ink">{i.assignee?.full_name ?? "Unassigned"}</dd>
            <dt className="text-ink-muted">Severity</dt>
            <dd className="text-ink">{SEVERITY[i.severity].label}</dd>
          </dl>
        )}
        {i.escalation_level ? (
          <p className="flex items-center gap-1.5 text-xs text-ink-secondary">
            <Clock className="size-3.5" aria-hidden /> Escalated {i.escalation_level} time{i.escalation_level > 1 ? "s" : ""}
          </p>
        ) : null}
      </PanelBody>
    </Panel>
  );
}

function describe(e: IncidentEvent): string {
  const d = e.details as Record<string, string | number | null | undefined>;
  switch (e.kind) {
    case "created":
      return `Opened (${d.severity})`;
    case "comment":
      return "Commented";
    case "assigned":
      return d.to ? "Assigned" : "Unassigned";
    case "status_changed":
      return `Moved from ${d.from} to ${d.to}`;
    case "severity_changed":
      return `Severity changed from ${d.from} to ${d.to}`;
    case "escalated":
      return `Escalated to managers (level ${d.level}): no response in time`;
    case "insight_linked":
      return `Linked to ${d.reference}`;
  }
}

function TimelinePanel({ incident: i }: { incident: IncidentDetail }) {
  const { workspace } = useWorkspace();
  const toast = useToast();
  const [body, setBody] = useState("");
  const comment = useIncidentMutation(() => api.post(`/incidents/${i.id}/comments`, { body }));
  return (
    <Panel flat aria-labelledby="timeline-title">
      <PanelHeader id="timeline-title" title="Timeline" description="Everything that happened, in order. Entries can't be edited." />
      <ol className="space-y-4 px-5 pb-5">
        {i.events.map((e) => (
          <li key={e.id} className="border-l-2 border-line pl-3">
            <p className="text-[13px] text-ink">
              <span className="font-medium">{e.actor_label}</span> · {describe(e)}
            </p>
            {e.body ? <p className="mt-1 text-sm whitespace-pre-wrap text-ink-secondary">{e.body}</p> : null}
            <p className="text-xs text-ink-muted">
              <time dateTime={e.created_at}>{formatDateTime(e.created_at)}</time>
            </p>
          </li>
        ))}
      </ol>
      {workspace.can("incidents.manage") ? (
        <form
          className="border-t border-line px-5 py-4"
          onSubmit={(e) => {
            e.preventDefault();
            if (!body.trim()) return;
            comment.mutate(undefined, {
              onSuccess: () => setBody(""),
              onError: (err) => toast({ tone: "danger", title: "Comment not added", description: errorMessage(err) }),
            });
          }}
        >
          <Field label="Add a comment">
            {(p) => (
              <textarea
                {...p}
                rows={3}
                value={body}
                maxLength={10000}
                onChange={(e) => setBody(e.target.value)}
                className="w-full rounded-control border border-line-control bg-raised px-3 py-2 text-sm text-ink hover:border-ink-secondary focus-visible:border-primary"
              />
            )}
          </Field>
          <div className="mt-2 flex justify-end">
            <Button type="submit" size="sm" disabled={!body.trim()} loading={comment.isPending}>
              Comment
            </Button>
          </div>
        </form>
      ) : null}
    </Panel>
  );
}
