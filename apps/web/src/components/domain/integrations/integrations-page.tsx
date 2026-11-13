"use client";

import { FileSpreadsheet, Plug, ShieldCheck } from "lucide-react";
import Link from "next/link";
import { useState } from "react";

import { Table, TableScroll, Td, Th, Tr } from "@/components/data-display/table";
import { EmptyState, ErrorState, PermissionDenied } from "@/components/feedback/states";
import { PageContainer, PageHeader } from "@/components/layout/page-header";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Panel, PanelHeader } from "@/components/ui/panel";
import { Skeleton } from "@/components/ui/skeleton";
import { type CatalogueEntry, useCatalogue, useConnections } from "@/features/integrations/api";
import { useWorkspace } from "@/features/workspace/workspace-context";
import { formatRelative } from "@/lib/format";

import { ConnectDialog } from "./connect-dialog";
import { CONNECTOR_LABEL, ConnectionStatusBadge } from "./status";

export function IntegrationsPage() {
  const { workspace } = useWorkspace();
  const canRead = workspace.can("integrations.read");
  const canManage = workspace.can("integrations.manage");
  const connections = useConnections();
  const catalogue = useCatalogue();
  const [connecting, setConnecting] = useState<CatalogueEntry | null>(null);

  if (!canRead) {
    return (
      <PageContainer>
        <PermissionDenied permission="integrations.read" />
      </PageContainer>
    );
  }

  return (
    <PageContainer>
      <PageHeader
        title="Integrations"
        description="Systems Operon reads operational data from. Credentials are encrypted and never shown again after you save them."
      />

      <Panel className="mt-6" aria-labelledby="connected-title">
        <PanelHeader id="connected-title" title="Connected systems" />
        {connections.isPending ? (
          <div role="status" aria-label="Loading" className="space-y-3 border-t border-line p-5">
            <Skeleton className="h-9 w-full" />
          </div>
        ) : connections.isError ? (
          <ErrorState compact onRetry={() => connections.refetch()} />
        ) : connections.data.length === 0 ? (
          <EmptyState
            compact
            icon={Plug}
            title="No systems connected yet"
            description={canManage ? "Connect a system below to start monitoring stock, sales and purchasing." : "An administrator can connect your systems."}
          />
        ) : (
          <TableScroll className="border-t border-line">
            <Table>
              <thead>
                <tr>
                  <Th>Name</Th>
                  <Th>System</Th>
                  <Th>Status</Th>
                  <Th>Last successful sync</Th>
                </tr>
              </thead>
              <tbody>
                {connections.data.map((c) => (
                  <Tr key={c.id}>
                    <Td className="font-medium">
                      <Link href={`/integrations/${c.id}`} className="underline-offset-4 hover:underline">
                        {c.name}
                      </Link>
                      {c.last_error ? <p className="max-w-md truncate text-xs font-normal text-ink-muted">{c.last_error}</p> : null}
                    </Td>
                    <Td className="text-ink-secondary">{CONNECTOR_LABEL[c.connector]}</Td>
                    <Td>
                      <ConnectionStatusBadge status={c.status} />
                    </Td>
                    <Td className="whitespace-nowrap text-ink-secondary">
                      {c.last_success_at ? formatRelative(c.last_success_at) : "Never"}
                    </Td>
                  </Tr>
                ))}
              </tbody>
            </Table>
          </TableScroll>
        )}
      </Panel>

      <section aria-labelledby="catalogue-title" className="mt-8">
        <h2 id="catalogue-title" className="text-[15px] font-semibold text-ink">
          Add a system
        </h2>
        <p className="mt-0.5 text-[13px] text-ink-muted">Operon reads data; it only writes back when an approved workflow asks it to.</p>
        {catalogue.isPending ? (
          <Skeleton className="mt-4 h-40 w-full" />
        ) : catalogue.data ? (
          <ul className="mt-4 grid grid-cols-1 gap-4 md:grid-cols-3">
            {catalogue.data.map((entry) => (
              <li key={entry.key} className="flex flex-col rounded-panel border border-line bg-raised p-5">
                <div className="flex items-center gap-3">
                  <span className="inline-flex size-9 items-center justify-center rounded-[8px] bg-sunken text-ink-secondary">
                    {entry.key === "csv" ? <FileSpreadsheet className="size-5" aria-hidden /> : <Plug className="size-5" aria-hidden />}
                  </span>
                  <h3 className="text-sm font-semibold text-ink">{entry.name}</h3>
                  {entry.verified_live ? null : <Badge tone="info" className="ml-auto">Not yet live-verified</Badge>}
                </div>
                <p className="mt-3 text-[13px] text-ink-secondary">{entry.description}</p>
                <p className="mt-3 text-xs text-ink-muted">Provides: {entry.provides.join(", ")}</p>
                {entry.supports_webhooks ? (
                  <p className="mt-1 inline-flex items-center gap-1 text-xs text-ink-muted">
                    <ShieldCheck className="size-3.5" aria-hidden /> Signed webhooks for instant updates
                  </p>
                ) : null}
                <div className="mt-auto pt-4">
                  {canManage ? (
                    <Button variant="secondary" size="sm" onClick={() => setConnecting(entry)}>
                      {entry.key === "csv" ? "Set up CSV import" : `Connect ${entry.name}`}
                    </Button>
                  ) : (
                    <p className="text-xs text-ink-muted">Only owners and administrators can connect systems.</p>
                  )}
                </div>
              </li>
            ))}
          </ul>
        ) : null}
      </section>

      <ConnectDialog entry={connecting} open={Boolean(connecting)} onOpenChange={(o) => !o && setConnecting(null)} />
    </PageContainer>
  );
}
