"use client";

import { useId } from "react";

import { Switch } from "@/components/ui/form";

/** A labelled on/off setting: title, explanation, switch. */
export function SwitchRow({
  label,
  hint,
  checked,
  onCheckedChange,
  disabled,
}: {
  label: string;
  hint: React.ReactNode;
  checked: boolean;
  onCheckedChange: (value: boolean) => void;
  disabled?: boolean;
}) {
  const id = useId();
  return (
    <div className="flex items-start justify-between gap-6">
      <div>
        <p id={`${id}-label`} className="text-sm font-medium text-ink">
          {label}
        </p>
        <p id={`${id}-hint`} className="mt-0.5 text-[13px] text-ink-muted">
          {hint}
        </p>
      </div>
      <Switch
        checked={checked}
        disabled={disabled}
        aria-labelledby={`${id}-label`}
        aria-describedby={`${id}-hint`}
        onCheckedChange={onCheckedChange}
      />
    </div>
  );
}
