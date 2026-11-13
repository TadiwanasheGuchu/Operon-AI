"use client";

import { X } from "lucide-react";
import { Dialog as D } from "radix-ui";

import { cn } from "@/lib/cn";

export const Dialog = D.Root;
export const DialogTrigger = D.Trigger;
export const DialogClose = D.Close;
export const DialogTitle = D.Title;
export const DialogDescription = D.Description;

export function DialogContent({
  className,
  children,
  hideClose = false,
  ...props
}: React.ComponentProps<typeof D.Content> & { hideClose?: boolean }) {
  return (
    <D.Portal>
      <D.Overlay className="fixed inset-0 z-40 bg-deep-sea/30 data-[state=open]:animate-[fade-in_var(--duration-base)_var(--ease-standard)]" />
      <D.Content
        className={cn(
          "fixed top-[12vh] left-1/2 z-50 w-[calc(100vw-32px)] max-w-lg -translate-x-1/2 rounded-dialog border border-line bg-raised shadow-dialog outline-none",
          "data-[state=open]:animate-[dialog-in_var(--duration-base)_var(--ease-standard)]",
          className,
        )}
        {...props}
      >
        {children}
        {hideClose ? null : (
          <D.Close
            className="absolute top-3 right-3 inline-flex size-8 items-center justify-center rounded-control text-ink-muted hover:bg-sunken hover:text-ink"
            aria-label="Close"
          >
            <X className="size-4" aria-hidden />
          </D.Close>
        )}
      </D.Content>
    </D.Portal>
  );
}

/** Edge-anchored drawer for contextual detail and the mobile navigation. */
export function DrawerContent({
  className,
  side = "left",
  children,
  ...props
}: React.ComponentProps<typeof D.Content> & { side?: "left" | "right" }) {
  return (
    <D.Portal>
      <D.Overlay className="fixed inset-0 z-40 bg-deep-sea/30 data-[state=open]:animate-[fade-in_var(--duration-base)_var(--ease-standard)]" />
      <D.Content
        className={cn(
          "fixed inset-y-0 z-50 flex w-[min(320px,calc(100vw-48px))] flex-col outline-none shadow-dialog",
          side === "left"
            ? "left-0 data-[state=open]:animate-[drawer-in-left_var(--duration-panel)_var(--ease-standard)]"
            : "right-0 data-[state=open]:animate-[drawer-in-right_var(--duration-panel)_var(--ease-standard)]",
          className,
        )}
        {...props}
      >
        {children}
      </D.Content>
    </D.Portal>
  );
}
