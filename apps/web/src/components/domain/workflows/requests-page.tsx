"use client";

import { Settings2, Workflow } from "lucide-react";
import Link from "next/link";
import { useState } from "react";

import { Pager } from "@/components/data-display/pager";
import { Table, TableScroll, Td, Th, Tr } from "@/components/data-display/table";
import { EmptyState, ErrorState, PermissionDenied } from "@/components/feedback/states";
import { PageContainer, PageHeader } from "@/components/layout/page-header";
import { Button } from "@/components/ui/button";
import { Panel } from "@/components/ui/panel";
import { Segmented } from "@/components/ui/segmented";
import { Skeleton } from "@/components/ui/skeleton";
import { type ExecutionFilter, PAGE_SIZE, useExecutions } from "@/features/workflows/api";
import { useWorkspace } from "@/features/workspace/workspace-context";
import { formatRelative } from "@/lib/format";

import { ExecutionStatusBadge } from "./status";

export function RequestsPage() {
  const { workspace } = useWorkspace();
  const [filter, setFilter] = useState<ExecutionFilter>("active");
  const [mine, setMine] = useState(false);
  const [page, setPage] = useState(0);
  const list = useExecutions(filter, mine, page);
  if (!workspace.can("workflows.read")) {
    return (
      <PageContainer>
        <PermissionDenied permission="workflows.read" />
      </PageContainer>
    );
  }
  const by = list.data?.by_status ?? {};
  const active = (by.awaiting_approval ?? 0) + (by.approved ?? 0) + (by.executing ?? 0);
  return (
    <PageContainer>
      <PageHeader
        title="Purchase requests"
        description="Raised from stockout insights, approved by people, then created as draft orders in your purchasing system. Every step is recorded."
        actions={
          <Button variant="secondary" asChild>
            <Link href="/workflows/settings">
              <Settings2 aria-hidden /> Approval policy
            </Link>
          </Button>
        }
      />
      <div className="mt-5 flex flex-wrap items-center gap-3">
        <Segmented
          label="Request status"
          value={filter}
          onChange={(v) => {
            setFilter(v);
            setPage(0);
          }}
          options={[
            { value: "active", label: "In progress", count: active },
            { value: "finished", label: "Finished" },
            { value: "all", label: "All" },
          ]}
        />
        <Segmented
          label="Requester"
          value={mine ? "mine" : "everyone"}
          onChange={(v) => {
            setMine(v === "mine");
            setPage(0);
          }}
          options={[
            { value: "everyone", label: "Everyone" },
            { value: "mine", label: "Mine" },
          ]}
        />
      </div>
      <Panel className="mt-4" aria-label="Purchase requests">
        {list.isPending ? (
          <div role="status" aria-label="Loading purchase requests" className="space-y-3 p-5">
            <Skeleton className="h-10 w-full" />
            <Skeleton className="h-10 w-full" />
          </div>
        ) : list.isError ? (
          <ErrorState compact onRetry={() => list.refetch()} />
        ) : list.data.items.length === 0 ? (
          <EmptyState
            compact
            icon={Workflow}
            title={filter === "active" ? "No requests in progress" : "Nothing here"}
            description="Open a stockout insight and choose “Create purchase request”."
          />
        ) : (
          <>
            <TableScroll>
              <Table>
                <thead>
                  <tr>
                    <Th>Request</Th>
                    <Th>Status</Th>
                    <Th numeric>Value</Th>
                    <Th>Requested by</Th>
                    <Th>Updated</Th>
                  </tr>
                </thead>
                <tbody>
                  {list.data.items.map((e) => (
                    <Tr key={e.id}>
                      <Td className="max-w-[460px] py-2.5">
                        <span className="font-mono text-[11px] text-ink-muted">
                          {e.reference}
                          {e.insight_reference ? ` · from ${e.insight_reference}` : ""}
                        </span>
                        <Link href={`/workflows/${e.id}`} className="block font-medium underline-offset-4 hover:underline">
                          {e.title}
                        </Link>
                        <span className="text-xs text-ink-muted">{e.supplier_name ?? "No supplier"}</span>
                      </Td>
                      <Td>
                        <ExecutionStatusBadge status={e.status} />
                        {e.current_stage ? <p className="mt-1 text-xs text-ink-muted">{e.current_stage}</p> : null}
                        {e.external_reference ? <p className="mt-1 font-mono text-[11px] text-ink-muted">{e.external_reference}</p> : null}
                      </Td>
                      <Td numeric className="whitespace-nowrap">
                        {e.value_display ?? "—"}
                      </Td>
                      <Td className="text-ink-secondary">{e.requested_by?.full_name ?? "Former member"}</Td>
                      <Td className="whitespace-nowrap text-ink-secondary">
                        <time dateTime={e.updated_at}>{formatRelative(e.updated_at)}</time>
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
