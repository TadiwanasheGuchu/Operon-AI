import { ArrowRightCircle, CircleCheck, CircleDot, CircleSlash, Eye, Gauge } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { type InsightStatus, STATUS_LABEL } from "@/features/intelligence/api";

const ICON = {
  open: CircleDot,
  acknowledged: Eye,
  actioned: ArrowRightCircle,
  resolved: CircleCheck,
  dismissed: CircleSlash,
} as const;
const TONE = {
  open: "info",
  acknowledged: "neutral",
  actioned: "info",
  resolved: "success",
  dismissed: "neutral",
} as const;

export function InsightStatusBadge({ status }: { status: InsightStatus }) {
  return (
    <Badge tone={TONE[status]} icon={ICON[status]}>
      {STATUS_LABEL[status]}
    </Badge>
  );
}

export function LowConfidenceBadge() {
  return (
    <Badge tone="warning" icon={Gauge}>
      Low confidence
    </Badge>
  );
}
