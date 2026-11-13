"use client";

import { Tooltip as T } from "radix-ui";

export function TooltipProvider({ children }: { children: React.ReactNode }) {
  return (
    <T.Provider delayDuration={300} skipDelayDuration={150}>
      {children}
    </T.Provider>
  );
}

export function Tooltip({
  content,
  children,
  side = "top",
}: {
  content: React.ReactNode;
  children: React.ReactNode;
  side?: "top" | "right" | "bottom" | "left";
}) {
  return (
    <T.Root>
      <T.Trigger asChild>{children}</T.Trigger>
      <T.Portal>
        <T.Content
          side={side}
          sideOffset={6}
          className="z-50 max-w-64 rounded-[6px] bg-deep-sea px-2 py-1 text-xs leading-4 text-ink-inverse shadow-popover data-[state=delayed-open]:animate-in"
        >
          {content}
        </T.Content>
      </T.Portal>
    </T.Root>
  );
}
