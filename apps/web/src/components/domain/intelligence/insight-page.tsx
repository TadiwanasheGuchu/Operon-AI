"use client";

import { ArrowLeft, ExternalLink, FileSearch, RefreshCw, Siren } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { Table, TableScroll, Td, Th, Tr } from "@/components/data-display/table";
import { ErrorState, PermissionDenied } from "@/components/feedback/states";
import { useToast } from "@/components/feedback/toast";
import { PageContainer } from "@/components/layout/page-header";
import { SEVERITY, SeverityBadge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogTitle, DrawerContent } from "@/components/ui/dialog";
import { Field, Input, Select } from "@/components/ui/form";
import { Panel, PanelBody, PanelHeader } from "@/components/ui/panel";
import { Skeleton } from "@/components/ui/skeleton";
import { useMembers } from "@/features/admin/api";
import {
  type Evidence,
  type InsightDetail,
  type InsightEvent,
  type InsightStatus,
  RULE_LABEL,
  useAISettings,
  useInsight,
  useInsightMutation,
  useSourceRecord,
} from "@/features/intelligence/api";
import type { IncidentDetail } from "@/features/incidents/api";
import { useWorkspace } from "@/features/workspace/workspace-context";
import { api, ApiRequestError, errorMessage } from "@/lib/api/client";
import { formatDateTime, formatRelative } from "@/lib/format";

import { ReasonDialog } from "./reason-dialog";
import { InsightStatusBadge, LowConfidenceBadge } from "./status";

export function InsightPage({ id }: { id: string }) {
  const { workspace } = useWorkspace();
  const insight = useInsight(id);

  if (!workspace.can("insights.read")) {
    return (
      <PageContainer>
        <PermissionDenied permission="insights.read" />
      </PageContainer>
    );
  }
  if (insight.isPending) {
    return (
      <PageContainer>
        <div role="status" aria-label="Loading insight" className="space-y-4">
          <Skeleton className="h-9 w-96 max-w-full" />
          <Skeleton className="h-48 w-full" />
        </div>
      </PageContainer>
    );
  }
  if (insight.isError) {
    const notFound = insight.error instanceof ApiRequestError && insight.error.status === 404;
    return (
      <PageContainer>
        <ErrorState
          title={notFound ? "This insight doesn't exist" : "The insight couldn't be loaded"}
          onRetry={notFound ? undefined : () => insight.refetch()}
        />
      </PageContainer>
    );
  }
  const i = insight.data;
  return (
    <PageContainer>
      <Link href="/intelligence" className="inline-flex items-center gap-1 text-[13px] text-ink-secondary hover:text-ink">
        <ArrowLeft className="size-4" aria-hidden /> Intelligence
      </Link>
      <Header insight={i} />
      <div className="mt-6 grid grid-cols-1 gap-5 xl:grid-cols-12">
        <div className="min-w-0 space-y-5 xl:col-span-8">
          <Explanation insight={i} />
          <EvidencePanel insight={i} />
          <Caveats insight={i} />
        </div>
        <div className="min-w-0 space-y-5 xl:col-span-4">
          <RecommendationPanel insight={i} />
          <OwnerPanel insight={i} />
          <Timeline events={i.events} />
        </div>
      </div>
    </PageContainer>
  );
}

const ACTION_LABEL: Partial<Record<InsightStatus, string>> = {
  acknowledged: "Acknowledge",
  actioned: "Mark actioned",
  resolved: "Resolve",
  dismissed: "Dismiss",
  open: "Reopen",
};

const DONE_LABEL: Record<InsightStatus, string> = {
  acknowledged: "Insight acknowledged",
  actioned: "Insight marked actioned",
  resolved: "Insight resolved",
  dismissed: "Insight dismissed",
  open: "Insight reopened",
};

function Header({ insight: i }: { insight: InsightDetail }) {
  const { workspace } = useWorkspace();
  const toast = useToast();
  const [asking, setAsking] = useState<"resolved" | "dismissed" | null>(null);
  const [escalating, setEscalating] = useState(false);
  const change = useInsightMutation((v: { status: InsightStatus; reason?: string }) =>
    api.post(`/insights/${i.id}/status`, v),
  );
  const canManage = workspace.can("insights.manage");
  const run = (status: InsightStatus, reason?: string) =>
    change.mutateAsync(
      { status, reason },
      {
        onSuccess: () => toast({ tone: "success", title: DONE_LABEL[status] }),
        onError: (e) => toast({ tone: "danger", title: "That didn't work", description: errorMessage(e) }),
      },
    );

  return (
    <div className="mt-3">
      <div className="flex flex-wrap items-center gap-2">
        <SeverityBadge severity={i.severity} />
        <InsightStatusBadge status={i.status} />
        {i.confidence === "low" ? <LowConfidenceBadge /> : null}
        <span className="font-mono text-[11px] text-ink-muted">
          {i.reference} · {RULE_LABEL[i.rule_id] ?? i.rule_id} v{i.rule_version}
        </span>
      </div>
      <div className="mt-2 flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
        <div className="min-w-0">
          <h1 className="font-display text-[28px] leading-9 font-medium text-ink">{i.title}</h1>
          <p className="mt-1 text-sm text-ink-secondary">{i.summary}</p>
          <p className="mt-1.5 text-xs text-ink-muted">
            {i.subject_label} · Detected <time dateTime={i.detected_at}>{formatDateTime(i.detected_at)}</time> · Last checked{" "}
            <time dateTime={i.last_evaluated_at}>{formatRelative(i.last_evaluated_at)}</time>
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          {canManage
            ? i.allowed_transitions.map((t) => (
                <Button
                  key={t}
                  variant={t === "dismissed" ? "tertiary" : "secondary"}
                  loading={change.isPending && change.variables?.status === t}
                  onClick={() => (t === "resolved" || t === "dismissed" ? setAsking(t) : run(t))}
                >
                  {ACTION_LABEL[t]}
                </Button>
              ))
            : null}
          {i.incident_id ? (
            <Button variant="secondary" asChild>
              <Link href={`/incidents/${i.incident_id}`}>
                <Siren aria-hidden /> View incident
              </Link>
            </Button>
          ) : workspace.can("incidents.manage") && i.status !== "resolved" && i.status !== "dismissed" ? (
            <Button onClick={() => setEscalating(true)}>
              <Siren aria-hidden /> Escalate to incident
            </Button>
          ) : null}
        </div>
      </div>
      {i.close_reason ? (
        <p className="mt-3 text-[13px] text-ink-secondary">
          <span className="font-medium text-ink">{i.status === "dismissed" ? "Dismissed:" : "Closed:"}</span> {i.close_reason}
          {i.suppressed_until ? ` Not raised again before ${formatDateTime(i.suppressed_until)} unless it gets worse.` : ""}
        </p>
      ) : null}
      <ReasonDialog
        open={asking === "dismissed"}
        onOpenChange={(o) => !o && setAsking(null)}
        title="Dismiss this insight"
        description="It won't be raised again for this item for 7 days unless it gets more severe. Say why, so others can see the reasoning."
        label="Reason"
        required
        confirmLabel="Dismiss"
        onSubmit={(reason) => run("dismissed", reason)}
      />
      <ReasonDialog
        open={asking === "resolved"}
        onOpenChange={(o) => !o && setAsking(null)}
        title="Resolve this insight"
        description="If the condition is still present at the next check, Operon raises a new insight."
        label="What was done"
        required={false}
        confirmLabel="Resolve"
        onSubmit={(reason) => run("resolved", reason || undefined)}
      />
      <EscalateDialog insight={i} open={escalating} onOpenChange={setEscalating} />
    </div>
  );
}

function EscalateDialog({
  insight: i,
  open,
  onOpenChange,
}: {
  insight: InsightDetail;
  open: boolean;
  onOpenChange: (o: boolean) => void;
}) {
  const { workspace } = useWorkspace();
  const toast = useToast();
  const router = useRouter();
  const members = useMembers(workspace.can("members.read") && open);
  const [assignee, setAssignee] = useState("");
  const [note, setNote] = useState("");
  const escalate = useInsightMutation(() =>
    api.post<IncidentDetail>(`/insights/${i.id}/incident`, { assignee_user_id: assignee || null, note }),
  );
  return (
    <Dialog open={open} onOpenChange={(o) => !escalate.isPending && onOpenChange(o)}>
      <DialogContent className="p-6">
        <DialogTitle className="text-base font-semibold text-ink">Escalate to an incident</DialogTitle>
        <DialogDescription className="mt-2 text-sm text-ink-secondary">
          Opens a {SEVERITY[i.severity].label.toLowerCase()}-severity incident linked to {i.reference}. Someone must start
          investigating within the response target, or it escalates to managers.
        </DialogDescription>
        <form
          className="mt-4 space-y-4"
          onSubmit={(e) => {
            e.preventDefault();
            escalate.mutate(undefined, {
              onSuccess: (inc) => {
                toast({ tone: "success", title: `${inc.reference} opened` });
                onOpenChange(false);
                router.push(`/incidents/${inc.id}`);
              },
              onError: (err) => toast({ tone: "danger", title: "The incident wasn't opened", description: errorMessage(err) }),
            });
          }}
        >
          <Field label="Assign to" hint={workspace.can("members.read") ? "Optional; you can assign later." : "You can assign it from the incident page."}>
            {(p) => (
              <Select {...p} value={assignee} onChange={(e) => setAssignee(e.target.value)} disabled={!members.data}>
                <option value="">Unassigned</option>
                {members.data?.map((m) => (
                  <option key={m.user_id} value={m.user_id}>
                    {m.full_name} ({m.role_name})
                  </option>
                ))}
              </Select>
            )}
          </Field>
          <Field label="Note" hint="Optional context for whoever picks it up.">
            {(p) => (
              <textarea
                {...p}
                rows={3}
                value={note}
                onChange={(e) => setNote(e.target.value)}
                className="w-full rounded-control border border-line-control bg-raised px-3 py-2 text-sm text-ink hover:border-ink-secondary focus-visible:border-primary"
              />
            )}
          </Field>
          <div className="flex justify-end gap-2">
            <Button type="button" variant="secondary" onClick={() => onOpenChange(false)}>
              Cancel
            </Button>
            <Button type="submit" loading={escalate.isPending}>
              Open incident
            </Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  );
}

function Explanation({ insight: i }: { insight: InsightDetail }) {
  const { workspace } = useWorkspace();
  const ai = useAISettings();
  const toast = useToast();
  const regenerate = useInsightMutation(() => api.post(`/insights/${i.id}/explain`));
  const ex = i.explanation;
  const canRegenerate =
    workspace.can("insights.manage") && ai.data?.enabled && ai.data.provider_available && (i.status === "open" || i.status === "acknowledged" || i.status === "actioned");
  return (
    <Panel flat aria-labelledby="explanation-title">
      <PanelHeader
        id="explanation-title"
        title="What happened"
        actions={
          canRegenerate ? (
            <Button
              variant="tertiary"
              size="sm"
              loading={regenerate.isPending || ex.pending}
              onClick={() =>
                regenerate.mutate(undefined, {
                  onError: (e) => toast({ tone: "danger", title: "Couldn't request a new explanation", description: errorMessage(e) }),
                })
              }
            >
              <RefreshCw aria-hidden /> Rewrite
            </Button>
          ) : undefined
        }
      />
      <PanelBody className="space-y-4">
        <p className="text-[15px] leading-6 text-ink">{ex.what_happened}</p>
        <div>
          <h3 className="text-xs font-semibold text-ink">Why it matters</h3>
          <p className="mt-1 text-sm text-ink-secondary">{ex.why_it_matters}</p>
        </div>
        <p className="border-t border-line pt-3 text-xs text-ink-muted">
          {ex.source === "model"
            ? `Written by ${ex.model ?? "a model"} from the evidence below, and checked: every number in it appears in the evidence.`
            : "Written from the rule's template. No AI model was used."}
          {ex.pending ? " A rewrite is in progress." : ""}
        </p>
      </PanelBody>
    </Panel>
  );
}

function EvidencePanel({ insight: i }: { insight: InsightDetail }) {
  const [open, setOpen] = useState<Evidence | null>(null);
  return (
    <Panel flat aria-labelledby="evidence-title">
      <PanelHeader
        id="evidence-title"
        title="Evidence"
        description="Synced values link to the record Operon holds; calculated values show their formula."
      />
      <TableScroll className="border-t border-line">
        <Table>
          <thead>
            <tr>
              <Th>Measure</Th>
              <Th numeric>Value</Th>
              <Th>Source</Th>
            </tr>
          </thead>
          <tbody>
            {i.evidence.map((e) => (
              <Tr key={e.id}>
                <Td className="text-ink-secondary">{e.label}</Td>
                <Td numeric className="font-medium whitespace-nowrap">
                  {e.value}
                </Td>
                <Td className="min-w-[220px]">
                  {e.resolvable ? (
                    <button
                      type="button"
                      onClick={() => setOpen(e)}
                      className="inline-flex items-center gap-1 text-left text-xs text-ink-secondary underline underline-offset-4 hover:text-ink"
                    >
                      <FileSearch className="size-3.5 shrink-0" aria-hidden />
                      {e.connection?.name ?? "Synced record"}
                      {e.source_ref ? <span className="font-mono text-[11px] text-ink-muted"> · {e.source_ref}</span> : null}
                    </button>
                  ) : e.formula ? (
                    <span className="font-mono text-[11px] text-ink-muted">{e.formula}</span>
                  ) : (
                    <span className="text-xs text-ink-muted">{e.source_type === "detector_config" ? "Detector setting" : "—"}</span>
                  )}
                </Td>
              </Tr>
            ))}
          </tbody>
        </Table>
      </TableScroll>
      <SourceDrawer insightId={i.id} evidence={open} onClose={() => setOpen(null)} />
    </Panel>
  );
}

const FIELD_LABEL: Record<string, string> = {
  on_hand: "On hand",
  reserved: "Reserved",
  as_of: "As of",
  received_quantity: "Received",
  expected_at: "Expected",
  ordered_at: "Ordered",
  lead_time_days: "Lead time (days)",
  min_quantity: "Minimum order",
  unit_price: "Unit price",
  purchase_order: "Purchase order",
  sku: "SKU",
  uom: "Unit",
};

function label(key: string): string {
  return FIELD_LABEL[key] ?? key.charAt(0).toUpperCase() + key.slice(1).replaceAll("_", " ");
}

function SourceDrawer({ insightId, evidence, onClose }: { insightId: string; evidence: Evidence | null; onClose: () => void }) {
  const source = useSourceRecord(insightId, evidence?.id ?? null);
  return (
    <Dialog open={Boolean(evidence)} onOpenChange={(o) => !o && onClose()}>
      <DrawerContent side="right" className="w-[min(440px,calc(100vw-32px))] overflow-y-auto border-l border-line bg-raised p-6">
        <DialogTitle className="pr-8 text-base font-semibold text-ink">{evidence?.label}</DialogTitle>
        <DialogDescription className="mt-1 text-[13px] text-ink-secondary">
          The record behind this value, as Operon holds it now.
        </DialogDescription>
        {source.isPending ? (
          <Skeleton className="mt-5 h-40 w-full" />
        ) : source.isError ? (
          <p className="mt-5 text-sm text-ink-secondary" role="alert">
            {errorMessage(source.error)}
          </p>
        ) : (
          <div className="mt-5 space-y-4 text-sm">
            <dl className="grid grid-cols-[minmax(0,2fr)_minmax(0,3fr)] gap-x-4 gap-y-2">
              <dt className="text-ink-muted">System</dt>
              <dd className="text-ink">
                {source.data.connection ? (
                  <Link href={`/integrations/${source.data.connection.id}`} className="inline-flex items-center gap-1 underline underline-offset-4">
                    {source.data.connection.name} <ExternalLink className="size-3.5" aria-hidden />
                  </Link>
                ) : (
                  "—"
                )}
              </dd>
              {source.data.external_id ? (
                <>
                  <dt className="text-ink-muted">Source reference</dt>
                  <dd className="font-mono text-xs text-ink">{source.data.external_id}</dd>
                </>
              ) : null}
              {Object.entries(source.data.fields)
                .filter(([k]) => k !== "daily_sales")
                .map(([k, v]) => (
                  <Field2 key={k} k={label(k)} v={v} />
                ))}
              {source.data.updated_at ? <Field2 k="Last updated in Operon" v={formatDateTime(source.data.updated_at)} /> : null}
            </dl>
            {Array.isArray(source.data.fields.daily_sales) ? <DailySales rows={source.data.fields.daily_sales as { day: string; quantity: string }[]} /> : null}
          </div>
        )}
      </DrawerContent>
    </Dialog>
  );
}

function Field2({ k, v }: { k: string; v: unknown }) {
  const text = v === null || v === undefined || v === "" ? "—" : String(v);
  return (
    <>
      <dt className="text-ink-muted">{k}</dt>
      <dd className="break-words text-ink">{/^\d{4}-\d{2}-\d{2}T/.test(text) ? formatDateTime(text) : text.replace(/\.0+$/, "").replace(/(\.\d*?)0+$/, "$1")}</dd>
    </>
  );
}

function DailySales({ rows }: { rows: { day: string; quantity: string }[] }) {
  return (
    <section aria-label="Daily sales">
      <h3 className="text-xs font-semibold text-ink">Daily sales (most recent first)</h3>
      <div className="mt-2 max-h-72 overflow-y-auto rounded-[10px] border border-line">
        <Table>
          <thead>
            <tr>
              <Th>Day</Th>
              <Th numeric>Units</Th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <Tr key={r.day}>
                <Td>{r.day}</Td>
                <Td numeric>{Number(r.quantity).toLocaleString("en-GB")}</Td>
              </Tr>
            ))}
          </tbody>
        </Table>
      </div>
    </section>
  );
}

function Caveats({ insight: i }: { insight: InsightDetail }) {
  if (!i.assumptions.length && !i.limitations.length) return null;
  return (
    <Panel flat aria-label="Assumptions and limitations">
      <PanelBody className="grid gap-5 pt-5 sm:grid-cols-2">
        <section>
          <h2 className="text-xs font-semibold text-ink">Assumptions</h2>
          {i.assumptions.length ? (
            <ul className="mt-1.5 list-disc space-y-1 pl-4 text-[13px] text-ink-secondary marker:text-icon">
              {i.assumptions.map((a) => (
                <li key={a}>{a}</li>
              ))}
            </ul>
          ) : (
            <p className="mt-1.5 text-[13px] text-ink-muted">None beyond the rule&apos;s formula.</p>
          )}
        </section>
        <section>
          <h2 className="text-xs font-semibold text-ink">Limitations</h2>
          {i.limitations.length ? (
            <ul className="mt-1.5 list-disc space-y-1 pl-4 text-[13px] text-ink-secondary marker:text-icon">
              {i.limitations.map((l) => (
                <li key={l}>{l}</li>
              ))}
            </ul>
          ) : (
            <p className="mt-1.5 text-[13px] text-ink-muted">None identified.</p>
          )}
        </section>
      </PanelBody>
    </Panel>
  );
}

function RecommendationPanel({ insight: i }: { insight: InsightDetail }) {
  const rec = i.recommendation;
  return (
    <Panel aria-labelledby="recommendation-title">
      <PanelHeader id="recommendation-title" title="Recommended action" description="Calculated by the rule, not by AI." />
      <PanelBody className="space-y-3">
        <p className="text-sm text-ink">{i.recommended_action}</p>
        {rec?.basis ? <p className="font-mono text-[11px] text-ink-muted">Quantity: {rec.basis}</p> : null}
        {rec?.action === "create_purchase_request" ? <RequestPurchase insight={i} /> : null}
      </PanelBody>
    </Panel>
  );
}

function RequestPurchase({ insight: i }: { insight: InsightDetail }) {
  const { workspace } = useWorkspace();
  const toast = useToast();
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [quantity, setQuantity] = useState(String(i.recommendation?.quantity ?? ""));
  const [note, setNote] = useState("");
  const [error, setError] = useState<string | undefined>();
  const submit = useInsightMutation(() =>
    api.post<{ id: string; reference: string }>("/purchase-requests", { insight_id: i.id, quantity: Number(quantity), note }),
  );
  const closed = i.status === "resolved" || i.status === "dismissed";
  const canRequest = workspace.can("workflows.request");
  const reason = closed
    ? "This insight is closed."
    : !canRequest
      ? "Requesting purchases needs the workflows.request permission."
      : null;
  return (
    <div className="flex flex-col items-start gap-1.5 border-t border-line pt-3">
      {reason ? (
        <>
          <Button size="sm" aria-disabled="true" aria-describedby="pr-unavailable" className="cursor-not-allowed bg-shallows text-ink-secondary hover:bg-shallows">
            Create purchase request
          </Button>
          <span id="pr-unavailable" className="text-xs text-ink-muted">
            {reason}
          </span>
        </>
      ) : (
        <>
          <Button size="sm" onClick={() => setOpen(true)}>
            Create purchase request
          </Button>
          <span className="text-xs text-ink-muted">Goes for approval first. Nothing is ordered until it&apos;s approved.</span>
        </>
      )}
      <Dialog open={open} onOpenChange={(o) => !submit.isPending && setOpen(o)}>
        <DialogContent className="p-6">
          <DialogTitle className="text-base font-semibold text-ink">Create purchase request</DialogTitle>
          <DialogDescription className="mt-2 text-sm text-ink-secondary">
            {i.subject_label}
            {i.recommendation?.supplier_name ? ` from ${i.recommendation.supplier_name}` : ""}. Product, supplier and price come from the
            insight; you can change the quantity. Approvers see the recommended quantity next to yours.
          </DialogDescription>
          <form
            className="mt-4 space-y-4"
            onSubmit={(e) => {
              e.preventDefault();
              const n = Number(quantity);
              if (!Number.isInteger(n) || n < 1 || n > 1_000_000) {
                setError("Enter a whole number from 1 to 1,000,000.");
                return;
              }
              submit.mutate(undefined, {
                onSuccess: (pr) => {
                  toast({ tone: "success", title: `${pr.reference} sent for approval` });
                  setOpen(false);
                  router.push(`/workflows/${pr.id}`);
                },
                onError: (err) => {
                  if (err instanceof ApiRequestError && err.code === "request_exists") {
                    const id = (err.details as { execution_id?: string }).execution_id;
                    if (id) router.push(`/workflows/${id}`);
                  }
                  toast({ tone: "danger", title: "Request not created", description: errorMessage(err) });
                },
              });
            }}
          >
            <Field
              label={`Quantity (${i.recommendation?.quantity_display?.replace(/^[\d,]+ /, "") ?? "units"})`}
              hint={`Recommended: ${i.recommendation?.quantity_display ?? "—"}. ${i.recommendation?.basis ?? ""}`}
              error={error}
            >
              {(p) => (
                <Input
                  {...p}
                  type="number"
                  inputMode="numeric"
                  min={1}
                  value={quantity}
                  onChange={(e) => {
                    setQuantity(e.target.value);
                    setError(undefined);
                  }}
                />
              )}
            </Field>
            <Field label="Note for approvers" hint="Optional">
              {(p) => (
                <textarea
                  {...p}
                  rows={3}
                  maxLength={2000}
                  value={note}
                  onChange={(e) => setNote(e.target.value)}
                  className="w-full rounded-control border border-line-control bg-raised px-3 py-2 text-sm text-ink hover:border-ink-secondary focus-visible:border-primary"
                />
              )}
            </Field>
            <div className="flex justify-end gap-2">
              <Button type="button" variant="secondary" onClick={() => setOpen(false)}>
                Cancel
              </Button>
              <Button type="submit" loading={submit.isPending}>
                Send for approval
              </Button>
            </div>
          </form>
        </DialogContent>
      </Dialog>
    </div>
  );
}

function OwnerPanel({ insight: i }: { insight: InsightDetail }) {
  const { workspace } = useWorkspace();
  const toast = useToast();
  const canAssign = workspace.can("insights.manage") && workspace.can("members.read");
  const members = useMembers(canAssign);
  const assign = useInsightMutation((userId: string | null) => api.put(`/insights/${i.id}/owner`, { user_id: userId }));
  return (
    <Panel aria-labelledby="owner-title">
      <PanelHeader id="owner-title" title="Owner" />
      <PanelBody>
        {canAssign ? (
          <Field label="Owner of this insight" hint="They're notified, and it appears under “Mine”.">
            {(p) => (
              <Select
                {...p}
                value={i.owner?.user_id ?? ""}
                disabled={!members.data || assign.isPending}
                onChange={(e) =>
                  assign.mutate(e.target.value || null, {
                    onSuccess: () => toast({ tone: "success", title: "Owner updated" }),
                    onError: (err) => toast({ tone: "danger", title: "Owner not changed", description: errorMessage(err) }),
                  })
                }
              >
                <option value="">Unassigned</option>
                {members.data?.map((m) => (
                  <option key={m.user_id} value={m.user_id}>
                    {m.full_name}
                  </option>
                ))}
              </Select>
            )}
          </Field>
        ) : (
          <p className="text-sm text-ink">{i.owner?.full_name ?? "Unassigned"}</p>
        )}
      </PanelBody>
    </Panel>
  );
}

function describeEvent(e: InsightEvent): string {
  const d = e.details as Record<string, string | null | undefined>;
  switch (e.kind) {
    case "detected":
      return `Detected (${d.severity})`;
    case "updated":
      return "Numbers changed at re-evaluation";
    case "severity_changed":
      return `Severity changed from ${d.from} to ${d.to}`;
    case "resolved":
      return (e.details as { automatic?: boolean }).automatic ? "Resolved automatically: no longer detected" : `Resolved${d.reason ? `: ${d.reason}` : ""}`;
    case "dismissed":
      return `Dismissed: ${d.reason}`;
    case "acknowledged":
      return d.reason ? `Acknowledged (${d.reason})` : "Acknowledged";
    case "actioned":
      return "Marked actioned";
    case "reopened":
      return "Reopened";
    case "owner_changed":
      return d.to ? "Owner assigned" : "Owner removed";
    case "escalated":
      return `Escalated to ${d.reference}`;
    case "explained":
      return `Explanation written by ${d.model}`;
    default:
      return e.kind;
  }
}

function Timeline({ events }: { events: InsightEvent[] }) {
  return (
    <Panel aria-labelledby="history-title">
      <PanelHeader id="history-title" title="History" />
      <ol className="space-y-3 px-5 pb-5">
        {[...events].reverse().map((e) => (
          <li key={e.id} className="border-l-2 border-line pl-3">
            <p className="text-[13px] text-ink">{describeEvent(e)}</p>
            <p className="text-xs text-ink-muted">
              {e.actor_label} · <time dateTime={e.created_at}>{formatDateTime(e.created_at)}</time>
            </p>
          </li>
        ))}
      </ol>
    </Panel>
  );
}

