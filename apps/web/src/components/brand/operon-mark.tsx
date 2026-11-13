import { cn } from "@/lib/cn";

/**
 * Operon mark: an open loop (connected systems, continuous operations) with a single
 * signal node in the gap (the detected condition that needs action). Monochrome by default;
 * `accent` colours the node. Legible from 16px.
 */
export function OperonMark({
  className,
  accent,
  title,
}: {
  className?: string;
  accent?: string;
  title?: string;
}) {
  return (
    <svg
      viewBox="0 0 32 32"
      className={cn("size-6 shrink-0", className)}
      role={title ? "img" : undefined}
      aria-hidden={title ? undefined : true}
      aria-label={title}
      fill="none"
    >
      <path
        d="M26.52 12.78 A11 11 0 1 1 19.22 5.48"
        stroke="currentColor"
        strokeWidth="4"
        strokeLinecap="round"
      />
      <circle cx="23.78" cy="8.22" r="2.75" fill={accent ?? "currentColor"} />
    </svg>
  );
}

export function OperonWordmark({ className }: { className?: string }) {
  return (
    <span className={cn("inline-flex items-center gap-2.5", className)}>
      <OperonMark accent="var(--color-sky)" />
      <span className="text-[17px] font-semibold tracking-[-0.015em]">Operon</span>
    </span>
  );
}
