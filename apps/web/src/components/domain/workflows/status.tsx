import { Ban, CircleCheck, CircleDot, CircleX, Clock, Hourglass, Send, ThumbsDown } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { EXECUTION_STATUS_LABEL, type Approval, type ExecutionStatus } from "@/features/workflows/api";

const ICON = {
  awaiting_approval: Clock,
  approved: CircleDot,
  executing: Send,
  completed: CircleCheck,
  rejected: ThumbsDown,
  expired: Hourglass,
  failed: CircleX,
  cancelled: Ban,
} as const;
const TONE = {
  awaiting_approval: "warning",
  approved: "info",
  executing: "info",
  completed: "success",
  rejected: "neutral",
  expired: "neutral",
  failed: "danger",
  cancelled: "neutral",
} as const;

export function ExecutionStatusBadge({ status }: { status: ExecutionStatus }) {
  return (
    <Badge tone={TONE[status]} icon={ICON[status]}>
      {EXECUTION_STATUS_LABEL[status]}
    </Badge>
  );
}

const STAGE_LABEL: Record<Approval["status"], string> = {
  waiting: "Not started",
  pending: "Waiting for decision",
  approved: "Approved",
  rejected: "Rejected",
  expired: "Expired",
  cancelled: "Cancelled",
};
const STAGE_TONE = {
  waiting: "neutral",
  pending: "warning",
  approved: "success",
  rejected: "danger",
  expired: "neutral",
  cancelled: "neutral",
} as const;
const STAGE_ICON = {
  waiting: Clock,
  pending: Hourglass,
  approved: CircleCheck,
  rejected: ThumbsDown,
  expired: Hourglass,
  cancelled: Ban,
} as const;

export function StageStatusBadge({ status }: { status: Approval["status"] }) {
  return (
    <Badge tone={STAGE_TONE[status]} icon={STAGE_ICON[status]}>
      {STAGE_LABEL[status]}
    </Badge>
  );
}
