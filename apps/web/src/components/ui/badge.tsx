import { cva, type VariantProps } from "class-variance-authority";
import {
  Ban,
  CircleCheck,
  CircleDashed,
  CircleDot,
  CircleX,
  Clock,
  PauseCircle,
  TriangleAlert,
  type LucideIcon,
} from "lucide-react";

import type { Severity } from "@/features/dashboard/contract";
import { cn } from "@/lib/cn";

const toneClasses = cva(
  "inline-flex items-center gap-1 rounded-[6px] px-1.5 py-0.5 text-xs font-medium leading-4 whitespace-nowrap [&_svg]:size-3.5 [&_svg]:shrink-0",
  {
    variants: {
      tone: {
        success: "bg-success-bg text-success",
        warning: "bg-warning-bg text-warning",
        danger: "bg-danger-bg text-danger",
        info: "bg-info-bg text-info",
        neutral: "bg-sunken text-ink-secondary",
      },
    },
    defaultVariants: { tone: "neutral" },
  },
);

type Tone = NonNullable<VariantProps<typeof toneClasses>["tone"]>;

export function Badge({
  tone,
  icon: Icon,
  children,
  className,
}: {
  tone?: Tone;
  icon?: LucideIcon;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <span className={cn(toneClasses({ tone }), className)}>
      {Icon ? <Icon aria-hidden strokeWidth={2} /> : null}
      {children}
    </span>
  );
}

export type Status =
  | "healthy"
  | "in_progress"
  | "pending"
  | "attention"
  | "failed"
  | "resolved"
  | "paused"
  | "disconnected";

const STATUS: Record<Status, { label: string; tone: Tone; icon: LucideIcon }> = {
  healthy: { label: "Healthy", tone: "success", icon: CircleCheck },
  in_progress: { label: "In progress", tone: "info", icon: CircleDot },
  pending: { label: "Pending", tone: "neutral", icon: Clock },
  attention: { label: "Needs attention", tone: "warning", icon: TriangleAlert },
  failed: { label: "Failed", tone: "danger", icon: CircleX },
  resolved: { label: "Resolved", tone: "success", icon: CircleCheck },
  paused: { label: "Paused", tone: "neutral", icon: PauseCircle },
  disconnected: { label: "Disconnected", tone: "danger", icon: Ban },
};

export function StatusBadge({ status, label }: { status: Status; label?: string }) {
  const s = STATUS[status];
  return (
    <Badge tone={s.tone} icon={s.icon}>
      {label ?? s.label}
    </Badge>
  );
}

export const SEVERITY: Record<Severity, { label: string; tone: Tone; icon: LucideIcon }> = {
  critical: { label: "Critical", tone: "danger", icon: CircleX },
  high: { label: "High", tone: "warning", icon: TriangleAlert },
  medium: { label: "Medium", tone: "info", icon: CircleDot },
  low: { label: "Low", tone: "neutral", icon: CircleDashed },
};

export function SeverityBadge({ severity }: { severity: Severity }) {
  const s = SEVERITY[severity];
  return (
    <Badge tone={s.tone} icon={s.icon}>
      {s.label}
    </Badge>
  );
}
