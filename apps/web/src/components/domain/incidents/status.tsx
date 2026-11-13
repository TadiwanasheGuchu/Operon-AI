import { CircleCheck, Search, TriangleAlert } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { INCIDENT_STATUS_LABEL, type IncidentStatus } from "@/features/incidents/api";

const ICON = { open: TriangleAlert, investigating: Search, resolved: CircleCheck } as const;
const TONE = { open: "warning", investigating: "info", resolved: "success" } as const;

export function IncidentStatusBadge({ status }: { status: IncidentStatus }) {
  return (
    <Badge tone={TONE[status]} icon={ICON[status]}>
      {INCIDENT_STATUS_LABEL[status]}
    </Badge>
  );
}
