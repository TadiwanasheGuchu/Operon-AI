"use client";

import { DropdownMenu as DM } from "radix-ui";

import { cn } from "@/lib/cn";

export const DropdownMenu = DM.Root;
export const DropdownMenuTrigger = DM.Trigger;
export const DropdownMenuGroup = DM.Group;

export function DropdownMenuContent({
  className,
  align = "end",
  sideOffset = 6,
  ...props
}: React.ComponentProps<typeof DM.Content>) {
  return (
    <DM.Portal>
      <DM.Content
        align={align}
        sideOffset={sideOffset}
        className={cn(
          "z-50 min-w-56 rounded-[10px] border border-line bg-raised p-1 text-sm text-ink shadow-popover",
          className,
        )}
        {...props}
      />
    </DM.Portal>
  );
}

export function DropdownMenuItem({
  className,
  ...props
}: React.ComponentProps<typeof DM.Item>) {
  return (
    <DM.Item
      className={cn(
        "flex cursor-default items-center gap-2 rounded-[6px] px-2 py-1.5 outline-none select-none",
        "data-[highlighted]:bg-sunken data-[disabled]:text-ink-muted data-[disabled]:pointer-events-none",
        "[&_svg]:size-4 [&_svg]:text-icon",
        className,
      )}
      {...props}
    />
  );
}

export function DropdownMenuLabel({
  className,
  ...props
}: React.ComponentProps<typeof DM.Label>) {
  return (
    <DM.Label
      className={cn("px-2 pt-1.5 pb-1 text-[11px] font-medium tracking-wide text-ink-muted uppercase", className)}
      {...props}
    />
  );
}

export function DropdownMenuSeparator() {
  return <DM.Separator className="-mx-1 my-1 h-px bg-line" />;
}
