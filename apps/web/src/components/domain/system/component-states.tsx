"use client";

import { Plus, Trash2 } from "lucide-react";
import { useState } from "react";

import { ProvenanceBadge } from "@/components/data-display/provenance-badge";
import { Table, TableScroll, Td, Th, Tr } from "@/components/data-display/table";
import { InlineAlert } from "@/components/feedback/inline-alert";
import { EmptyState, ErrorState, PermissionDenied } from "@/components/feedback/states";
import { IntegrationsIcon } from "@/components/icons";
import { SeverityBadge, StatusBadge, type Status } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Kbd } from "@/components/ui/kbd";
import { Panel, PanelBody, PanelHeader } from "@/components/ui/panel";
import { Skeleton } from "@/components/ui/skeleton";
import { Tooltip } from "@/components/ui/tooltip";

const STATUSES: Status[] = ["healthy", "in_progress", "pending", "attention", "failed", "resolved", "paused", "disconnected"];

/** Living reference for every reusable state. Internal page: shown in demo and development only. */
export function ComponentStates() {
  const [loading, setLoading] = useState(false);
  const [retried, setRetried] = useState(0);

  return (
    <div className="mx-auto max-w-[1200px] px-4 pt-6 pb-12 md:px-6 lg:px-9 lg:pt-8">
      <h1 className="font-display text-[30px] leading-9 font-medium text-ink">Component states</h1>
      <p className="mt-1 max-w-2xl text-sm text-ink-muted">
        Every reusable state in the Operon interface. Use these instead of one-off treatments so loading, empty,
        error, success, disabled and permission states read the same everywhere.
      </p>

      <div className="mt-6 grid grid-cols-1 gap-5 lg:grid-cols-2">
        <Panel aria-labelledby="buttons">
          <PanelHeader id="buttons" title="Buttons" description="Primary for the one main action per view." />
          <PanelBody className="space-y-4">
            <Row label="Variants">
              <Button>Primary</Button>
              <Button variant="secondary">Secondary</Button>
              <Button variant="tertiary">Tertiary</Button>
              <Button variant="destructive">
                <Trash2 aria-hidden /> Delete
              </Button>
              <Tooltip content="Add item">
                <Button variant="quiet" size="icon" aria-label="Add item">
                  <Plus aria-hidden />
                </Button>
              </Tooltip>
            </Row>
            <Row label="Disabled">
              <Button disabled>Primary</Button>
              <Button variant="secondary" disabled>
                Secondary
              </Button>
              <Button variant="tertiary" disabled>
                Tertiary
              </Button>
            </Row>
            <Row label="Loading">
              <Button
                loading={loading}
                onClick={() => {
                  setLoading(true);
                  setTimeout(() => setLoading(false), 1500);
                }}
              >
                {loading ? "Saving…" : "Save changes"}
              </Button>
              <Button size="sm" variant="secondary">
                Small
              </Button>
            </Row>
            <p className="text-xs text-ink-muted">
              Press <Kbd>Tab</Kbd> to see focus rings. Every control has a visible focus state.
            </p>
          </PanelBody>
        </Panel>

        <Panel aria-labelledby="badges">
          <PanelHeader id="badges" title="Status, severity and provenance" description="Colour is always paired with an icon and words." />
          <PanelBody className="space-y-4">
            <Row label="Status">
              {STATUSES.map((s) => (
                <StatusBadge key={s} status={s} />
              ))}
            </Row>
            <Row label="Severity">
              <SeverityBadge severity="critical" />
              <SeverityBadge severity="high" />
              <SeverityBadge severity="medium" />
              <SeverityBadge severity="low" />
            </Row>
            <Row label="Data provenance">
              <ProvenanceBadge provenance="live" />
              <ProvenanceBadge provenance="demo" />
              <ProvenanceBadge provenance="stale" />
              <ProvenanceBadge provenance="unavailable" />
            </Row>
          </PanelBody>
        </Panel>

        <Panel aria-labelledby="alerts" className="lg:col-span-2">
          <PanelHeader id="alerts" title="Feedback" description="Say what happened and what the user can do next." />
          <PanelBody className="grid gap-3 md:grid-cols-2">
            <InlineAlert tone="success" title="Purchase request PR-3307 submitted">
              Finance Manager approval is required above £5,000. You&apos;ll be notified of the decision.
            </InlineAlert>
            <InlineAlert tone="info" title="Odoo synchronisation in progress">
              Insights will refresh when it completes.
            </InlineAlert>
            <InlineAlert
              tone="warning"
              title="Shopify access token expires in 3 days"
              action={
                <Button size="sm" variant="secondary" aria-disabled="true">
                  Reconnect
                </Button>
              }
            >
              Order data stops flowing when it expires.
            </InlineAlert>
            <InlineAlert tone="danger" title="Purchase request could not be created in Odoo">
              Odoo rejected the supplier reference. Nothing was created; the workflow can be retried safely.
            </InlineAlert>
          </PanelBody>
        </Panel>

        <Panel aria-labelledby="loading">
          <PanelHeader id="loading" title="Loading" description="Skeletons mirror the final layout." />
          <PanelBody className="space-y-3" role="status" aria-label="Example loading state">
            <Skeleton className="h-4 w-40" />
            <Skeleton className="h-16 w-full" />
            <Skeleton className="h-4 w-56" />
          </PanelBody>
        </Panel>

        <Panel aria-labelledby="empty">
          <PanelHeader id="empty" title="Empty" />
          <EmptyState
            compact
            icon={IntegrationsIcon}
            title="No integrations connected"
            description="Connect your ERP or sales channel to start monitoring stock and orders."
          />
        </Panel>

        <Panel aria-labelledby="error">
          <PanelHeader id="error" title="Error" />
          <ErrorState
            compact
            description={retried ? `Still failing after ${retried} retr${retried > 1 ? "ies" : "y"}. Contact your administrator.` : undefined}
            requestId="3f9c1d2e8a7b4c6d9e0f1a2b3c4d5e6f"
            onRetry={() => setRetried((n) => n + 1)}
          />
        </Panel>

        <Panel aria-labelledby="permission">
          <PanelHeader id="permission" title="Permission denied" />
          <PermissionDenied compact permission="workflows.approve" />
        </Panel>

        <Panel aria-labelledby="table" className="lg:col-span-2">
          <PanelHeader id="table" title="Table" description="Numeric columns right-aligned with tabular figures." />
          <TableScroll className="border-t border-line">
            <Table>
              <thead>
                <tr>
                  <Th>Purchase order</Th>
                  <Th>Supplier</Th>
                  <Th>Status</Th>
                  <Th numeric>Lines</Th>
                  <Th numeric>Value</Th>
                </tr>
              </thead>
              <tbody>
                {[
                  ["PO-10482", "Brightline Safety Supplies", "in_progress", 1, "£9,700"],
                  ["PO-10391", "Kestrel Packaging", "attention", 4, "£18,240"],
                  ["PO-10388", "Northgate Pallets", "resolved", 12, "£3,105"],
                ].map(([po, supplier, status, lines, value]) => (
                  <Tr key={po as string}>
                    <Td className="font-mono text-xs">{po}</Td>
                    <Td>{supplier}</Td>
                    <Td>
                      <StatusBadge status={status as Status} />
                    </Td>
                    <Td numeric>{lines}</Td>
                    <Td numeric>{value}</Td>
                  </Tr>
                ))}
              </tbody>
            </Table>
          </TableScroll>
        </Panel>
      </div>
    </div>
  );
}

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <p className="mb-2 text-[11px] font-medium tracking-[0.06em] text-ink-muted uppercase">{label}</p>
      <div className="flex flex-wrap items-center gap-2">{children}</div>
    </div>
  );
}
