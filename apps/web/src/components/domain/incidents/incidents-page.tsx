"use client";

import { Plus, Siren } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { Pager } from "@/components/data-display/pager";
import { Table, TableScroll, Td, Th, Tr } from "@/components/data-display/table";
import { EmptyState, ErrorState, PermissionDenied } from "@/components/feedback/states";
import { useToast } from "@/components/feedback/toast";
import { PageContainer, PageHeader } from "@/components/layout/page-header";
import { Badge, SEVERITY, SeverityBadge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogTitle } from "@/components/ui/dialog";
import { Field, Input, Select } from "@/components/ui/form";
import { Panel } from "@/components/ui/panel";
import { Segmented } from "@/components/ui/segmented";
import { Skeleton } from "@/components/ui/skeleton";
import { useMembers } from "@/features/admin/api";
import type { Severity } from "@/features/dashboard/contract";
import {
  type IncidentDetail,
  type IncidentFilter,
  PAGE_SIZE,
  RESPONSE_TARGET_LABEL,
  useIncidentMutation,
  useIncidents,
} from "@/features/incidents/api";
import { useWorkspace } from "@/features/workspace/workspace-context";
import { api, errorMessage } from "@/lib/api/client";
import { formatDateTime, formatRelative } from "@/lib/format";

import { IncidentStatusBadge } from "./status";

export function IncidentsPage() {
  const { workspace } = useWorkspace();
  const [filter, setFilter] = useState<IncidentFilter>("unresolved");
  const [assignee, setAssignee] = useState<"" | "me" | "none">("");
  const [page, setPage] = useState(0);
  const [creating, setCreating] = useState(false);
  const list = useIncidents(filter, assignee, page);

  if (!workspace.can("incidents.read")) {
    return (
      <PageContainer>
        <PermissionDenied permission="incidents.read" />
      </PageContainer>
    );
  }
  const counts = list.data?.unresolved_by_severity ?? {};
  const unresolved = Object.values(counts).reduce((a, b) => a + (b ?? 0), 0);
  return (
    <PageContainer>
      <PageHeader
        title="Incidents"
        description="Problems someone owns until they're resolved. Open incidents escalate to managers if nobody starts investigating within the response target."
        actions={
          workspace.can("incidents.manage") ? (
            <Button onClick={() => setCreating(true)}>
              <Plus aria-hidden /> New incident
            </Button>
          ) : null
        }
      />
      <div className="mt-5 flex flex-wrap items-center gap-3">
        <Segmented
          label="Incident status"
          value={filter}
          onChange={(v) => {
            setFilter(v);
            setPage(0);
          }}
          options={[
            { value: "unresolved", label: "Unresolved", count: unresolved },
            { value: "resolved", label: "Resolved" },
            { value: "all", label: "All" },
          ]}
        />
        <label className="sr-only" htmlFor="assignee-filter">
          Assignee
        </label>
        <Select
          id="assignee-filter"
          className="h-9 w-44"
          value={assignee}
          onChange={(e) => {
            setAssignee(e.target.value as "" | "me" | "none");
            setPage(0);
          }}
        >
          <option value="">Anyone</option>
          <option value="me">Assigned to me</option>
          <option value="none">Unassigned</option>
        </Select>
      </div>
      <Panel className="mt-4" aria-label="Incidents">
        {list.isPending ? (
          <div role="status" aria-label="Loading incidents" className="space-y-3 p-5">
            <Skeleton className="h-10 w-full" />
            <Skeleton className="h-10 w-full" />
          </div>
        ) : list.isError ? (
          <ErrorState compact onRetry={() => list.refetch()} />
        ) : list.data.items.length === 0 ? (
          <EmptyState
            compact
            icon={Siren}
            title={filter === "unresolved" ? "No unresolved incidents" : "Nothing here"}
            description="Escalate an insight, or open an incident for anything else that needs an owner."
          />
        ) : (
          <>
            <TableScroll>
              <Table>
                <thead>
                  <tr>
                    <Th>Severity</Th>
                    <Th>Incident</Th>
                    <Th>Status</Th>
                    <Th>Assignee</Th>
                    <Th>Response</Th>
                  </tr>
                </thead>
                <tbody>
                  {list.data.items.map((i) => (
                    <Tr key={i.id}>
                      <Td>
                        <SeverityBadge severity={i.severity} />
                      </Td>
                      <Td className="max-w-[480px] py-2.5">
                        <span className="font-mono text-[11px] text-ink-muted">{i.reference}</span>
                        {i.insight ? <span className="ml-2 font-mono text-[11px] text-ink-muted">from {i.insight.reference}</span> : null}
                        <Link href={`/incidents/${i.id}`} className="block font-medium underline-offset-4 hover:underline">
                          {i.title}
                        </Link>
                      </Td>
                      <Td>
                        <IncidentStatusBadge status={i.status} />
                      </Td>
                      <Td className="text-ink-secondary">{i.assignee?.full_name ?? "Unassigned"}</Td>
                      <Td className="whitespace-nowrap text-xs">
                        {i.status === "open" ? (
                          i.response_overdue ? (
                            <Badge tone="danger">Overdue · escalated {i.escalation_level}×</Badge>
                          ) : (
                            <span className="text-ink-secondary">Due {formatDateTime(i.response_due_at)}</span>
                          )
                        ) : i.status === "resolved" && i.resolved_at ? (
                          <span className="text-ink-muted">Resolved {formatRelative(i.resolved_at)}</span>
                        ) : (
                          <span className="text-ink-muted">Being investigated</span>
                        )}
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
      <NewIncidentDialog open={creating} onOpenChange={setCreating} />
    </PageContainer>
  );
}

function NewIncidentDialog({ open, onOpenChange }: { open: boolean; onOpenChange: (o: boolean) => void }) {
  const { workspace } = useWorkspace();
  const toast = useToast();
  const router = useRouter();
  const members = useMembers(workspace.can("members.read") && open);
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [severity, setSeverity] = useState<Severity>("medium");
  const [assignee, setAssignee] = useState("");
  const [error, setError] = useState<string | undefined>();
  const create = useIncidentMutation(() =>
    api.post<IncidentDetail>("/incidents", { title, description, severity, assignee_user_id: assignee || null }),
  );
  return (
    <Dialog open={open} onOpenChange={(o) => !create.isPending && onOpenChange(o)}>
      <DialogContent className="p-6">
        <DialogTitle className="text-base font-semibold text-ink">New incident</DialogTitle>
        <DialogDescription className="mt-2 text-sm text-ink-secondary">
          For a problem that isn&apos;t an insight yet. Response target: {RESPONSE_TARGET_LABEL[severity]}.
        </DialogDescription>
        <form
          className="mt-4 space-y-4"
          onSubmit={(e) => {
            e.preventDefault();
            if (title.trim().length < 3) {
              setError("Give it a short title (at least 3 characters).");
              return;
            }
            create.mutate(undefined, {
              onSuccess: (inc) => {
                toast({ tone: "success", title: `${inc.reference} opened` });
                onOpenChange(false);
                router.push(`/incidents/${inc.id}`);
              },
              onError: (err) => toast({ tone: "danger", title: "Not opened", description: errorMessage(err) }),
            });
          }}
        >
          <Field label="Title" error={error}>
            {(p) => (
              <Input
                {...p}
                value={title}
                maxLength={300}
                onChange={(e) => {
                  setTitle(e.target.value);
                  setError(undefined);
                }}
              />
            )}
          </Field>
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label="Severity">
              {(p) => (
                <Select {...p} value={severity} onChange={(e) => setSeverity(e.target.value as Severity)}>
                  {(["critical", "high", "medium", "low"] as const).map((s) => (
                    <option key={s} value={s}>
                      {SEVERITY[s].label}
                    </option>
                  ))}
                </Select>
              )}
            </Field>
            <Field label="Assign to">
              {(p) => (
                <Select {...p} value={assignee} onChange={(e) => setAssignee(e.target.value)} disabled={!members.data}>
                  <option value="">Unassigned</option>
                  {members.data?.map((m) => (
                    <option key={m.user_id} value={m.user_id}>
                      {m.full_name}
                    </option>
                  ))}
                </Select>
              )}
            </Field>
          </div>
          <Field label="Description" hint="What's happening, and what's affected.">
            {(p) => (
              <textarea
                {...p}
                rows={4}
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                className="w-full rounded-control border border-line-control bg-raised px-3 py-2 text-sm text-ink hover:border-ink-secondary focus-visible:border-primary"
              />
            )}
          </Field>
          <div className="flex justify-end gap-2">
            <Button type="button" variant="secondary" onClick={() => onOpenChange(false)}>
              Cancel
            </Button>
            <Button type="submit" loading={create.isPending}>
              Open incident
            </Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  );
}
