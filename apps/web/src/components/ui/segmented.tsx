"use client";

import { ToggleGroup } from "radix-ui";

import { cn } from "@/lib/cn";

/** Single-choice filter (e.g. Active / Closed / All). Keyboard: arrow keys move, Space selects. */
export function Segmented<T extends string>({
  value,
  onChange,
  options,
  label,
}: {
  value: T;
  onChange: (value: T) => void;
  options: { value: T; label: string; count?: number }[];
  label: string;
}) {
  return (
    <ToggleGroup.Root
      type="single"
      value={value}
      onValueChange={(v) => v && onChange(v as T)}
      aria-label={label}
      className="inline-flex h-9 items-center rounded-control border border-line bg-raised p-0.5"
    >
      {options.map((o) => (
        <ToggleGroup.Item
          key={o.value}
          value={o.value}
          className={cn(
            "h-full rounded-[6px] px-3 text-[13px] text-ink-secondary transition-colors transition-standard hover:text-ink",
            "data-[state=on]:bg-selected data-[state=on]:font-medium data-[state=on]:text-ink",
          )}
        >
          {o.label}
          {o.count !== undefined ? <span className="ml-1.5 tnum text-ink-muted">{o.count}</span> : null}
        </ToggleGroup.Item>
      ))}
    </ToggleGroup.Root>
  );
}
