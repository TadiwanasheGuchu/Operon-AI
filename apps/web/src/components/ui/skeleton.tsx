import { cn } from "@/lib/cn";

export function Skeleton({ className }: { className?: string }) {
  return (
    <div
      aria-hidden
      className={cn("animate-pulse rounded-[6px] bg-mist/70 motion-reduce:animate-none", className)}
    />
  );
}
