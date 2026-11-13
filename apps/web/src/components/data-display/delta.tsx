import { ArrowDownRight, ArrowUpRight, Minus } from "lucide-react";

import { cn } from "@/lib/cn";

/**
 * Change versus the previous period. Direction is shown with an arrow and words, so meaning
 * never depends on colour alone. `increaseIs` decides whether up is good or bad.
 */
export function Delta({
  value,
  previous,
  increaseIs,
  periodLabel,
}: {
  value: number;
  previous: number | null;
  increaseIs: "good" | "bad" | "neutral";
  periodLabel: string;
}) {
  if (previous === null) return null;
  const diff = value - previous;
  const Icon = diff > 0 ? ArrowUpRight : diff < 0 ? ArrowDownRight : Minus;
  const good = increaseIs === "neutral" || diff === 0 ? null : (diff > 0) === (increaseIs === "good");
  return (
    <span
      className={cn(
        "inline-flex items-center gap-0.5 text-xs tnum",
        good === null ? "text-ink-muted" : good ? "text-success" : "text-danger",
      )}
    >
      <Icon className="size-3.5" aria-hidden />
      <span>
        {diff === 0 ? "No change" : `${diff > 0 ? "+" : "−"}${Math.abs(diff)}`}
        <span className="text-ink-muted"> vs {periodLabel}</span>
      </span>
    </span>
  );
}
