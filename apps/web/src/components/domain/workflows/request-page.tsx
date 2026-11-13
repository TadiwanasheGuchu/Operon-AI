"use client";

import { ArrowLeft, Radar } from "lucide-react";
import Link from "next/link";
import { useState } from "react";

import { ErrorState, PermissionDenied } from "@/components/feedback/states";
import { InlineAlert } from "@/components/feedback/inline-alert";
import { useToast } from "@/components/feedback/toast";
import { PageContainer } from "@/components/layout/page-header";
import { Button } from "@/components/ui/button";
import { Panel, PanelBody, PanelHeader } from "@/components/ui/panel";
import { Skeleton } from "@/components/ui/skeleton";
import { type Approval, type ExecutionDetail, useExecution, useWorkflowMutation } from "@/features/workflows/api";
import { useWorkspace } from "@/features/workspace/workspace-context";
import { api, ApiRequestError, errorMessage } from "@/lib/api/client";
import { formatDateTime } from "@/lib/format";

import { ReasonDialog } from "../intelligence/reason-dialog";
import { DecisionDialog } from "./decision-dialog";
import { ExecutionStatusBadge, StageStatusBadge } from "./status";

export function RequestPage({ id }: { id: string }) {
  const { workspace } = useWorkspace();
  const execution = useExecution(id);
  if (!workspace.can("workflows.read")) {
    return (
      <PageContainer>
        <PermissionDenied permission="workflows.read" />
      </PageContainer>
    );
  }
  if (execution.isPending) {
    return (
      <PageContainer>
        <div role="status" aria-label="Loading purchase request" className="space-y-4">
          <Skeleton className="h-9 w-96 max-w-full" />
          <Skeleton className="h-48 w-full" />
        </div>
      </PageContainer>
    );
  }
  if (execution.isError) {
    const notFound = execution.error instanceof ApiRequestError && execution.error.status === 404;
    return (
      <PageContainer>
        <ErrorState
          title={notFound ? "This purchase request doesn't exist" : "The purchase request couldn't be loaded"}
          onRetry={notFound ? undefined : () => execution.refetch()}
        />
      </PageContainer>
    );
  }
  const e = execution.data;
  return (
    <PageContainer>
      <Link href="/workflows" className="inline-flex items-center gap-1 text-[13px] text-ink-secondary hover:text-ink">
        <ArrowLeft className="size-4" aria-hidden /> Purchase requests
      </Link>
      <Header execution={e} />
      <Outcome execution={e} />
      <div className="mt-6 grid grid-cols-1 gap-5 xl:grid-cols-12">
        <div className="min-w-0 space-y-5 xl:col-span-7">
          <Stages execution={e} />
          <Timeline execution={e} />
        </div>
        <div className="min-w-0 space-y-5 xl:col-span-5">
          <Details execution={e} />
        </div>
      </div>
    </PageContainer>
  );
}

function Header({ execution: e }: { execution: ExecutionDetail }) {
  const toast = useToast();
  const [cancelling, setCancelling] = useState(false);
  const cancel = useWorkflowMutation((reason: string) => api.post(`/purchase-requests/${e.id}/cancel`, { reason }));
  const retry = useWorkflowMutation(() => api.post(`/purchase-requests/${e.id}/retry`));
  return (
    <div className="mt-3">
      <div className="flex flex-wrap items-center gap-2">
        <ExecutionStatusBadge status={e.status} />
        <span className="font-mono text-[11px] text-ink-muted">
          {e.reference} · policy v{e.policy_version}
        </span>
      </div>
      <div className="mt-2 flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
        <div className="min-w-0">
          <h1 className="font-display text-[28px] leading-9 font-medium text-ink">{e.title}</h1>
          <p className="mt-1 text-sm text-ink-secondary">
            {e.supplier_name ?? "No supplier"} · {e.value_display ?? "value not known"}
          </p>
          <p className="mt-1.5 text-xs text-ink-muted">
            Requested by {e.requested_by?.full_name ?? "a former member"} on{" "}
            <time dateTime={e.created_at}>{formatDateTime(e.created_at)}</time>
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          {e.can_retry ? (
            <Button
              loading={retry.isPending}
              onClick={() =>
                retry.mutate(undefined, {
                  onSuccess: () => toast({ tone: "success", title: "Retrying" }),
                  onError: (err) => toast({ tone: "danger", title: "Couldn't retry", description: errorMessage(err) }),
                })
              }
            >
              Retry
            </Button>
          ) : null}
          {e.can_cancel ? (
            <Button variant="secondary" onClick={() => setCancelling(true)}>
              Cancel request
            </Button>
          ) : null}
        </div>
      </div>
      <ReasonDialog
        open={cancelling}
        onOpenChange={setCancelling}
        title={`Cancel ${e.reference}`}
        description="Approvers are no longer asked, and nothing is sent to the purchasing system."
        label="Reason"
        required={false}
        confirmLabel="Cancel request"
        onSubmit={(reason) =>
          cancel.mutateAsync(reason, {
            onSuccess: () => toast({ tone: "success", title: `${e.reference} cancelled` }),
            onError: (err) => toast({ tone: "danger", title: "Not cancelled", description: errorMessage(err) }),
          })
        }
      />
    </div>
  );
}

function Outcome({ execution: e }: { execution: ExecutionDetail }) {
  if (e.status === "completed") {
    return e.result.mode === "odoo" ? (
      <InlineAlert className="mt-5" tone="success" title={`Draft purchase order ${e.result.reference} created in ${e.input.target_name}`}>
        It&apos;s a draft (request for quotation): confirm it in {e.input.target_name} to send it to the supplier.
      </InlineAlert>
    ) : (
      <InlineAlert className="mt-5" tone="success" title="Approved and recorded in Operon">
        {e.input.target_reason} Raise this order in your purchasing system.
      </InlineAlert>
    );
  }
  if (e.status === "failed") {
    return (
      <InlineAlert className="mt-5" tone="danger" title="Couldn't create the order">
        {e.error} {e.can_retry ? "Fix the cause, then retry: the order won't be duplicated." : "A workflow manager can retry it."}
      </InlineAlert>
    );
  }
  if (e.status === "executing" && e.error) {
    return (
      <InlineAlert className="mt-5" tone="warning" title={`Attempt ${e.attempts} failed; retrying automatically`}>
        {e.error}
      </InlineAlert>
    );
  }
  return null;
}

function Stages({ execution: e }: { execution: ExecutionDetail }) {
  const [deciding, setDeciding] = useState<{ approval: Approval; decision: "approve" | "reject" } | null>(null);
  return (
    <Panel flat aria-labelledby="stages-title">
      <PanelHeader id="stages-title" title="Approvals" description="Decided in order. Each stage needs a different person, and never the requester." />
      <ol className="divide-y divide-line border-t border-line">
        {e.approvals.map((a) => (
          <li key={a.id} className="px-5 py-4">
            <div className="flex flex-wrap items-center gap-2">
              <span className="text-sm font-medium text-ink">
                {a.stage}. {a.name}
              </span>
              <StageStatusBadge status={a.status} />
            </div>
            <p className="mt-1 text-xs text-ink-muted">
              {a.reason} Approvers: {a.approver_role_names.join(", ")}.
            </p>
            {a.decided_by ? (
              <p className="mt-1.5 text-[13px] text-ink-secondary">
                {a.status === "approved" ? "Approved" : "Rejected"} by {a.decided_by.full_name}
                {a.decided_at ? ` on ${formatDateTime(a.decided_at)}` : ""}
                {a.comment ? `: “${a.comment}”` : ""}
              </p>
            ) : null}
            {a.status === "pending" ? (
              <div className="mt-2.5 flex flex-wrap items-center gap-2">
                {a.due_at ? (
                  <span className="text-xs text-ink-secondary">
                    {a.escalated_at ? "Reminder sent · " : ""}Decide by {formatDateTime(a.due_at)}
                  </span>
                ) : null}
                {a.blocked_reason === null ? (
                  <span className="ml-auto flex gap-2">
                    <Button variant="secondary" size="sm" onClick={() => setDeciding({ approval: a, decision: "reject" })}>
                      Reject
                    </Button>
                    <Button size="sm" onClick={() => setDeciding({ approval: a, decision: "approve" })}>
                      Approve
                    </Button>
                  </span>
                ) : (
                  <span className="text-xs text-ink-muted">{a.blocked_reason}</span>
                )}
              </div>
            ) : null}
          </li>
        ))}
      </ol>
      {deciding ? (
        <DecisionDialog
          execution={e}
          approval={deciding.approval}
          decision={deciding.decision}
          onOpenChange={(o) => !o && setDeciding(null)}
        />
      ) : null}
    </Panel>
  );
}

function Timeline({ execution: e }: { execution: ExecutionDetail }) {
  return (
    <Panel flat aria-labelledby="timeline-title">
      <PanelHeader id="timeline-title" title="Execution history" description="Every step, in order. Entries can't be edited." />
      <ol className="space-y-3 px-5 pb-5">
        {e.events.map((ev) => (
          <li key={ev.id} className="border-l-2 border-line pl-3">
            <p className="text-[13px] text-ink">{ev.message}</p>
            <p className="text-xs text-ink-muted">
              {ev.actor_label} · <time dateTime={ev.created_at}>{formatDateTime(ev.created_at)}</time>
            </p>
          </li>
        ))}
      </ol>
    </Panel>
  );
}

function Details({ execution: e }: { execution: ExecutionDetail }) {
  const i = e.input;
  const rows: [string, React.ReactNode][] = [
    ["Product", `${i.product_name}${i.sku ? ` (${i.sku})` : ""}`],
    ["Location", i.location_name ?? "All locations"],
    ["Supplier", i.supplier_name ?? "Not set"],
    [
      "Quantity",
      `${i.quantity.toLocaleString("en-GB")} ${i.uom}` +
        (i.recommended_quantity !== null && i.recommended_quantity !== i.quantity
          ? ` (recommended ${i.recommended_quantity.toLocaleString("en-GB")})`
          : ""),
    ],
    ["Unit price", i.unit_price && i.currency ? `${i.currency} ${Number(i.unit_price).toFixed(2)}` : "Not known"],
    ["Value", i.value_display ?? "Not known"],
    ["Sent to", i.target_name ?? "Recorded in Operon only"],
  ];
  return (
    <Panel aria-labelledby="details-title">
      <PanelHeader id="details-title" title="Request" description="Fixed when it was submitted." />
      <PanelBody className="space-y-4">
        <dl className="grid grid-cols-[minmax(0,2fr)_minmax(0,3fr)] gap-x-4 gap-y-2 text-sm">
          {rows.map(([k, v]) => (
            <div key={k} className="contents">
              <dt className="text-ink-muted">{k}</dt>
              <dd className="text-ink">{v}</dd>
            </div>
          ))}
        </dl>
        {i.note ? (
          <div>
            <h3 className="text-xs font-semibold text-ink">Requester&apos;s note</h3>
            <p className="mt-1 text-sm whitespace-pre-wrap text-ink-secondary">{i.note}</p>
          </div>
        ) : null}
        {e.insight_id ? (
          <Link href={`/intelligence/${e.insight_id}`} className="inline-flex items-center gap-1.5 text-[13px] text-ink-secondary underline underline-offset-4">
            <Radar className="size-3.5" aria-hidden /> Raised from {i.insight_reference}
          </Link>
        ) : null}
      </PanelBody>
    </Panel>
  );
}
