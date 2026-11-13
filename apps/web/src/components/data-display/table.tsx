import { cn } from "@/lib/cn";

/** Dense, scannable table primitives. Wrap in <TableScroll> for horizontal overflow on small screens. */
export function TableScroll({ className, ...props }: React.ComponentProps<"div">) {
  return <div className={cn("overflow-x-auto", className)} {...props} />;
}

export function Table({ className, ...props }: React.ComponentProps<"table">) {
  return <table className={cn("w-full border-collapse text-[13px]", className)} {...props} />;
}

export function Th({
  className,
  numeric,
  ...props
}: React.ComponentProps<"th"> & { numeric?: boolean }) {
  return (
    <th
      scope="col"
      className={cn(
        "h-9 border-b border-line px-3 text-xs font-medium whitespace-nowrap text-ink-muted first:pl-5 last:pr-5",
        numeric ? "text-right" : "text-left",
        className,
      )}
      {...props}
    />
  );
}

export function Td({
  className,
  numeric,
  ...props
}: React.ComponentProps<"td"> & { numeric?: boolean }) {
  return (
    <td
      className={cn(
        "h-11 border-b border-line px-3 align-middle text-ink first:pl-5 last:pr-5",
        numeric && "text-right tnum",
        className,
      )}
      {...props}
    />
  );
}

export function Tr({ className, ...props }: React.ComponentProps<"tr">) {
  return (
    <tr
      className={cn("transition-colors transition-standard hover:bg-sunken/60 [&:last-child>td]:border-b-0", className)}
      {...props}
    />
  );
}
