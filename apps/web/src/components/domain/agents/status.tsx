import { CircleCheck, CircleSlash, CircleX, Gauge, LoaderCircle } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { RUN_STATUS_LABEL, type RunStatus } from "@/features/agents/api";

const ICON = { running: LoaderCircle, succeeded: CircleCheck, limited: Gauge, refused: CircleSlash, failed: CircleX } as const;
const TONE = { running: "info", succeeded: "success", limited: "warning", refused: "neutral", failed: "danger" } as const;

export function RunStatusBadge({ status }: { status: RunStatus }) {
  return (
    <Badge tone={TONE[status]} icon={ICON[status]}>
      {RUN_STATUS_LABEL[status]}
    </Badge>
  );
}
