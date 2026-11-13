"use client";

import { ClipboardCheck } from "lucide-react";
import Link from "next/link";
import { useState } from "react";

import { EmptyState, ErrorState, PermissionDenied } from "@/components/feedback/states";
import { PageContainer, PageHeader } from "@/components/layout/page-header";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Panel } from "@/components/ui/panel";
import { Segmented } from "@/components/ui/segmented";
import { Skeleton } from "@/components/ui/skeleton";
import { type InboxItem, useInbox } from "@/features/workflows/api";
import { useWorkspace } from "@/features/workspace/workspace-context";
import { formatDateTime, formatRelative } from "@/lib/format";

import { DecisionDialog } from "./decision-dialog";

export function ApprovalsPage() {
  const { workspace } = useWorkspace();
  const inbox = useInbox();
  const [scope, setScope] = useState<"mine" | "all">("mine");
  const [deciding, setDeciding] = useState<{ item: InboxItem; decision: "approve" | "reject" } | null>(null);

  if (!workspace.can("workflows.read")) {
    return (
      <PageContainer>
        <PermissionDenied permission="workflows.read" />
      </PageContainer>
    );
  }
  const items = inbox.data ?? [];
  const mine = items.filter((i) => i.approval.blocked_reason === null);
  const shown = scope === "mine" ? mine : items;
  return (
    <PageContainer narrow>
      <PageHeader
        title="Approvals"
        description="Requests waiting for a decision. You can't approve your own requests, or two stages of the same request."
      />
      <div className="mt-5">
        <Segmented
          label="Which approvals"
          value={scope}
          onChange={setScope}
          options={[
            { value: "mine", label: "Waiting for me", count: mine.length },
            { value: "all", label: "All pending", count: items.length },
          ]}
        />
      </div>
      <Panel className="mt-4" aria-label="Pending approvals">
        {inbox.isPending ? (
          <div role="status" aria-label="Loading approvals" className="space-y-3 p-5">
            <Skeleton className="h-16 w-full" />
            <Skeleton className="h-16 w-full" />
          </div>
        ) : inbox.isError ? (
          <ErrorState compact onRetry={() => inbox.refetch()} />
        ) : shown.length === 0 ? (
          <EmptyState
            compact
            icon={ClipboardCheck}
            title={scope === "mine" ? "Nothing is waiting for you" : "Nothing is waiting for a decision"}
            description={scope === "mine" && items.length ? "Other requests are waiting for someone in a different role." : undefined}
          />
        ) : (
          <ul className="divide-y divide-line">
            {shown.map((item) => {
              const { approval: a, execution: e } = item;
              const overdue = a.due_at !== null && new Date(a.due_at) < new Date();
              return (
                <li key={a.id} className="flex flex-col gap-3 px-5 py-4 sm:flex-row sm:items-start sm:justify-between">
                  <div className="min-w-0">
                    <div className="flex flex-wrap items-center gap-2 text-xs text-ink-muted">
                      <span className="font-mono text-[11px]">{e.reference}</span>
                      <span>{a.name}</span>
                      {a.escalated_at ? <Badge tone="warning">Reminder sent</Badge> : null}
                      {overdue ? <Badge tone="danger">Overdue</Badge> : null}
                    </div>
                    <Link href={`/workflows/${e.id}`} className="mt-1 block text-sm font-medium text-ink underline-offset-4 hover:underline">
                      {e.title}
                    </Link>
                    <p className="mt-0.5 text-[13px] text-ink-secondary">
                      {e.value_display ?? "Value not known"}
                      {e.supplier_name ? ` · ${e.supplier_name}` : ""} · requested by {e.requested_by?.full_name ?? "a former member"}{" "}
                      <time dateTime={e.created_at}>{formatRelative(e.created_at)}</time>
                    </p>
                    <p className="mt-1 text-xs text-ink-muted">
                      {a.reason} Approvers: {a.approver_role_names.join(", ")}.
                      {a.due_at ? ` Decide by ${formatDateTime(a.due_at)}.` : ""}
                    </p>
                    {a.blocked_reason ? <p className="mt-1 text-xs text-ink-secondary">{a.blocked_reason}</p> : null}
                  </div>
                  {a.blocked_reason === null ? (
                    <div className="flex shrink-0 gap-2">
                      <Button variant="secondary" size="sm" onClick={() => setDeciding({ item, decision: "reject" })}>
                        Reject
                      </Button>
                      <Button size="sm" onClick={() => setDeciding({ item, decision: "approve" })}>
                        Approve
                      </Button>
                    </div>
                  ) : null}
                </li>
              );
            })}
          </ul>
        )}
      </Panel>
      {deciding ? (
        <DecisionDialog
          execution={deciding.item.execution}
          approval={deciding.item.approval}
          decision={deciding.decision}
          onOpenChange={(o) => !o && setDeciding(null)}
        />
      ) : null}
    </PageContainer>
  );
}
