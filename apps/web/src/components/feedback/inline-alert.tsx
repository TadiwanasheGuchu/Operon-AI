import { CircleCheck, CircleX, Info, TriangleAlert, type LucideIcon } from "lucide-react";

import { cn } from "@/lib/cn";

type Tone = "info" | "success" | "warning" | "danger";

const TONES: Record<Tone, { icon: LucideIcon; classes: string; role: "status" | "alert" }> = {
  info: { icon: Info, classes: "bg-info-bg text-info border-info/20", role: "status" },
  success: { icon: CircleCheck, classes: "bg-success-bg text-success border-success/20", role: "status" },
  warning: { icon: TriangleAlert, classes: "bg-warning-bg text-warning border-warning/20", role: "status" },
  danger: { icon: CircleX, classes: "bg-danger-bg text-danger border-danger/20", role: "alert" },
};

/** Explains what happened and what the user can do next. */
export function InlineAlert({
  tone = "info",
  title,
  children,
  action,
  className,
}: {
  tone?: Tone;
  title: string;
  children?: React.ReactNode;
  action?: React.ReactNode;
  className?: string;
}) {
  const t = TONES[tone];
  const Icon = t.icon;
  return (
    <div
      role={t.role}
      className={cn("flex gap-3 rounded-[10px] border px-3.5 py-3 text-sm", t.classes, className)}
    >
      <Icon className="mt-0.5 size-4 shrink-0" aria-hidden />
      <div className="min-w-0 flex-1">
        <p className="font-medium">{title}</p>
        {children ? <div className="mt-0.5 text-ink-secondary">{children}</div> : null}
      </div>
      {action ? <div className="shrink-0 self-center">{action}</div> : null}
    </div>
  );
}
