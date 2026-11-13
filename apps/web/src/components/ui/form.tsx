"use client";

import { forwardRef, useId } from "react";

import { cn } from "@/lib/cn";

const controlBase =
  "w-full rounded-control border border-line-control bg-raised px-3 text-sm text-ink placeholder:text-ink-muted " +
  "transition-colors transition-standard hover:border-ink-secondary focus-visible:border-primary " +
  "disabled:cursor-not-allowed disabled:bg-sunken disabled:text-ink-muted aria-[invalid=true]:border-danger";

export const Input = forwardRef<HTMLInputElement, React.ComponentProps<"input">>(function Input(
  { className, ...props },
  ref,
) {
  return <input ref={ref} className={cn(controlBase, "h-10", className)} {...props} />;
});

export const Select = forwardRef<HTMLSelectElement, React.ComponentProps<"select">>(function Select(
  { className, children, ...props },
  ref,
) {
  return (
    <select ref={ref} className={cn(controlBase, "h-10 pr-8", className)} {...props}>
      {children}
    </select>
  );
});

/**
 * Label + control + hint + error, wired for assistive technology.
 * The child receives id / aria-describedby / aria-invalid via render prop.
 */
export function Field({
  label,
  hint,
  error,
  children,
  className,
}: {
  label: string;
  hint?: React.ReactNode;
  error?: string;
  className?: string;
  children: (props: { id: string; "aria-describedby"?: string; "aria-invalid"?: boolean }) => React.ReactNode;
}) {
  const id = useId();
  const hintId = hint ? `${id}-hint` : undefined;
  const errorId = error ? `${id}-error` : undefined;
  const describedBy = [hintId, errorId].filter(Boolean).join(" ") || undefined;
  return (
    <div className={cn("space-y-1.5", className)}>
      <label htmlFor={id} className="block text-[13px] font-medium text-ink">
        {label}
      </label>
      {children({ id, "aria-describedby": describedBy, "aria-invalid": error ? true : undefined })}
      {hint ? (
        <p id={hintId} className="text-xs text-ink-muted">
          {hint}
        </p>
      ) : null}
      {error ? (
        <p id={errorId} className="text-xs font-medium text-danger">
          {error}
        </p>
      ) : null}
    </div>
  );
}

export function Switch({
  checked,
  onCheckedChange,
  disabled,
  ...props
}: {
  checked: boolean;
  onCheckedChange: (value: boolean) => void;
  disabled?: boolean;
} & Omit<React.ComponentProps<"button">, "onChange">) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      disabled={disabled}
      onClick={() => onCheckedChange(!checked)}
      className={cn(
        "relative inline-flex h-6 w-10 shrink-0 items-center rounded-full border transition-colors transition-standard",
        "disabled:cursor-not-allowed disabled:opacity-50",
        checked ? "border-primary bg-primary" : "border-line-control bg-sunken",
      )}
      {...props}
    >
      <span
        aria-hidden
        className={cn(
          "inline-block size-4 rounded-full bg-raised shadow-sm transition-transform transition-standard",
          checked ? "translate-x-[19px]" : "translate-x-[3px]",
        )}
      />
    </button>
  );
}
