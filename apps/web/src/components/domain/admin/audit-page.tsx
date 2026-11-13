"use client";

import { useInfiniteQuery } from "@tanstack/react-query";
import { ChevronDown } from "lucide-react";
import { Fragment, useState } from "react";

import { Table, TableScroll, Td, Th, Tr } from "@/components/data-display/table";
import { EmptyState, ErrorState, PermissionDenied } from "@/components/feedback/states";
import { PageContainer, PageHeader } from "@/components/layout/page-header";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Select } from "@/components/ui/form";
import { Panel } from "@/components/ui/panel";
import { Skeleton } from "@/components/ui/skeleton";
import type { AuditEvent } from "@/features/admin/api";
import { useActiveOrganisation } from "@/features/session/use-session";
import { useWorkspace } from "@/features/workspace/workspace-context";
import { api } from "@/lib/api/client";
import { formatDateTime } from "@/lib/format";
import { cn } from "@/lib/cn";

const FAMILIES = [
  { value: "", label: "All activity" },
  { value: "member.", label: "Members" },
  { value: "invitation.", label: "Invitations" },
  { value: "organisation.", label: "Organisation settings" },
  { value: "access.", label: "Access denied" },
];

const ACTION_LABELS: Record<string, string> = {
  "organisation.created": "created the organisation",
  "organisation.updated": "changed organisation settings",
  "member.joined": "joined",
  "member.role_changed": "changed a member's role",
  "member.removed": "removed a member",
  "invitation.created": "invited someone",
  "invitation.revoked": "withdrew an invitation",
  "invitation.accepted": "accepted an invitation",
  "access.denied": "was denied access",
};

export function AuditPage() {
  const { workspace } = useWorkspace();
  const org = useActiveOrganisation();
  const allowed = workspace.can("audit.read");
  const [family, setFamily] = useState("");
  const [outcome, setOutcome] = useState("");

  const query = useInfiniteQuery({
    queryKey: ["tenant", org?.id, "audit", family, outcome],
    enabled: allowed && Boolean(org),
    initialPageParam: null as string | null,
    queryFn: ({ pageParam }) => {
      const params = new URLSearchParams({ limit: "50" });
      if (pageParam) params.set("cursor", pageParam);
      if (family) params.set("action", family);
      if (outcome) params.set("outcome", outcome);
      return api.get<{ items: AuditEvent[]; next_cursor: string | null }>(`/audit?${params}`);
    },
    getNextPageParam: (last) => last.next_cursor,
  });

  if (!allowed) {
    return (
      <PageContainer>
        <PermissionDenied permission="audit.read" />
      </PageContainer>
    );
  }
  const events = query.data?.pages.flatMap((p) => p.items) ?? [];

  return (
    <PageContainer>
      <PageHeader
        title="Audit log"
        description="A permanent record of changes and access decisions in this organisation. Entries can't be edited or deleted."
      />
      <div className="mt-6 flex flex-wrap gap-2" role="group" aria-label="Filters">
        <Select aria-label="Activity" className="h-9 w-56" value={family} onChange={(e) => setFamily(e.target.value)}>
          {FAMILIES.map((f) => (
            <option key={f.value} value={f.value}>
              {f.label}
            </option>
          ))}
        </Select>
        <Select aria-label="Outcome" className="h-9 w-44" value={outcome} onChange={(e) => setOutcome(e.target.value)}>
          <option value="">Any outcome</option>
          <option value="success">Succeeded</option>
          <option value="denied">Denied</option>
          <option value="failure">Failed</option>
        </Select>
      </div>
      <Panel className="mt-3">
        {query.isPending ? (
          <div role="status" aria-label="Loading audit log" className="space-y-3 p-5">
            {Array.from({ length: 5 }, (_, i) => (
              <Skeleton key={i} className="h-9 w-full" />
            ))}
          </div>
        ) : query.isError ? (
          <ErrorState compact onRetry={() => query.refetch()} />
        ) : events.length === 0 ? (
          <EmptyState compact title="No matching activity" description="Try a different filter." />
        ) : (
          <TableScroll>
            <Table>
              <thead>
                <tr>
                  <Th>When</Th>
                  <Th>Who</Th>
                  <Th>What</Th>
                  <Th>Outcome</Th>
                  <Th className="w-10">
                    <span className="sr-only">Details</span>
                  </Th>
                </tr>
              </thead>
              <tbody>
                {events.map((e) => (
                  <AuditRow key={e.id} event={e} />
                ))}
              </tbody>
            </Table>
          </TableScroll>
        )}
      </Panel>
      {query.hasNextPage ? (
        <div className="mt-4 flex justify-center">
          <Button variant="secondary" loading={query.isFetchingNextPage} onClick={() => query.fetchNextPage()}>
            Load older entries
          </Button>
        </div>
      ) : null}
    </PageContainer>
  );
}

function AuditRow({ event }: { event: AuditEvent }) {
  const [open, setOpen] = useState(false);
  const hasDetails = Object.keys(event.details).length > 0 || event.request_id;
  return (
    <Fragment>
      <Tr>
        <Td className="font-mono text-[11px] whitespace-nowrap text-ink-muted">
          <time dateTime={event.occurred_at}>{formatDateTime(event.occurred_at)}</time>
        </Td>
        <Td className="max-w-56 truncate" title={event.actor_label}>
          {event.actor_label}
        </Td>
        <Td>
          <span className="text-ink-secondary">{ACTION_LABELS[event.action] ?? event.action}</span>
          <span className="ml-2 font-mono text-[11px] text-ink-muted">{event.action}</span>
        </Td>
        <Td>
          {event.outcome === "success" ? (
            <Badge tone="success">Succeeded</Badge>
          ) : event.outcome === "denied" ? (
            <Badge tone="warning">Denied</Badge>
          ) : (
            <Badge tone="danger">Failed</Badge>
          )}
        </Td>
        <Td>
          {hasDetails ? (
            <Button
              variant="quiet"
              size="icon-sm"
              aria-expanded={open}
              aria-label={open ? "Hide details" : "Show details"}
              onClick={() => setOpen((o) => !o)}
            >
              <ChevronDown aria-hidden className={cn("transition-transform transition-standard", open && "rotate-180")} />
            </Button>
          ) : null}
        </Td>
      </Tr>
      {open ? (
        <tr>
          <td colSpan={5} className="border-b border-line bg-canvas px-5 py-3">
            <dl className="grid gap-x-6 gap-y-1 font-mono text-[11px] sm:grid-cols-[max-content_1fr]">
              {Object.entries(event.details).map(([k, v]) => (
                <Fragment key={k}>
                  <dt className="text-ink-muted">{k}</dt>
                  <dd className="break-all text-ink">{typeof v === "string" ? v : JSON.stringify(v)}</dd>
                </Fragment>
              ))}
              {event.target_type ? (
                <>
                  <dt className="text-ink-muted">target</dt>
                  <dd className="text-ink">
                    {event.target_type} {event.target_id}
                  </dd>
                </>
              ) : null}
              {event.request_id ? (
                <>
                  <dt className="text-ink-muted">request</dt>
                  <dd className="text-ink">{event.request_id}</dd>
                </>
              ) : null}
            </dl>
          </td>
        </tr>
      ) : null}
    </Fragment>
  );
}
