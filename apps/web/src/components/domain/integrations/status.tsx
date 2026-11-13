import { StatusBadge, type Status } from "@/components/ui/badge";
import type { ConnectionStatus } from "@/features/integrations/api";

const MAP: Record<ConnectionStatus, { status: Status; label: string }> = {
  active: { status: "healthy", label: "Healthy" },
  syncing: { status: "in_progress", label: "Syncing" },
  degraded: { status: "attention", label: "Sync failing" },
  action_required: { status: "failed", label: "Needs attention" },
  paused: { status: "paused", label: "Paused" },
};

export function ConnectionStatusBadge({ status }: { status: ConnectionStatus }) {
  const s = MAP[status];
  return <StatusBadge status={s.status} label={s.label} />;
}

export const CONNECTOR_LABEL: Record<string, string> = { odoo: "Odoo", shopify: "Shopify", csv: "CSV import" };
