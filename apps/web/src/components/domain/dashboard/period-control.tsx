"use client";

import { ToggleGroup } from "radix-ui";

import { periods, type Period } from "@/features/dashboard/contract";
import { cn } from "@/lib/cn";

export const PERIOD_LABEL: Record<Period, string> = { "7d": "7 days", "30d": "30 days", "90d": "90 days" };
export const PERIOD_PREVIOUS: Record<Period, string> = {
  "7d": "previous 7 days",
  "30d": "previous 30 days",
  "90d": "previous 90 days",
};

export function PeriodControl({ value, onChange }: { value: Period; onChange: (p: Period) => void }) {
  return (
    <ToggleGroup.Root
      type="single"
      value={value}
      onValueChange={(v) => v && onChange(v as Period)}
      aria-label="Reporting period"
      className="inline-flex h-9 items-center rounded-control border border-line bg-raised p-0.5"
    >
      {periods.map((p) => (
        <ToggleGroup.Item
          key={p}
          value={p}
          className={cn(
            "h-full rounded-[6px] px-3 text-[13px] text-ink-secondary transition-colors transition-standard hover:text-ink",
            "data-[state=on]:bg-selected data-[state=on]:font-medium data-[state=on]:text-ink",
          )}
        >
          {PERIOD_LABEL[p]}
        </ToggleGroup.Item>
      ))}
    </ToggleGroup.Root>
  );
}
