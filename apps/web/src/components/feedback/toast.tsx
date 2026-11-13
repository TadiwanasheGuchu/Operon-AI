"use client";

import { CircleCheck, CircleX, Info, X } from "lucide-react";
import { Toast as T } from "radix-ui";
import { createContext, useCallback, useContext, useMemo, useState } from "react";

import { cn } from "@/lib/cn";

type Tone = "success" | "danger" | "info";
interface ToastItem {
  id: number;
  tone: Tone;
  title: string;
  description?: string;
}

const ToastContext = createContext<(toast: Omit<ToastItem, "id">) => void>(() => {});

const ICON = { success: CircleCheck, danger: CircleX, info: Info };
const TONE = { success: "text-success", danger: "text-danger", info: "text-info" };

/** Confirmations after an action. Announced politely to screen readers; errors assertively. */
export function ToastProvider({ children }: { children: React.ReactNode }) {
  const [items, setItems] = useState<ToastItem[]>([]);
  const push = useCallback((toast: Omit<ToastItem, "id">) => {
    setItems((list) => [...list.slice(-2), { ...toast, id: Date.now() + Math.random() }]);
  }, []);
  const value = useMemo(() => push, [push]);
  return (
    <ToastContext.Provider value={value}>
      <T.Provider swipeDirection="right" duration={5000}>
        {children}
        {items.map((t) => {
          const Icon = ICON[t.tone];
          return (
            <T.Root
              key={t.id}
              type={t.tone === "danger" ? "foreground" : "background"}
              onOpenChange={(open) => !open && setItems((list) => list.filter((x) => x.id !== t.id))}
              className="flex items-start gap-3 rounded-[10px] border border-line bg-raised p-3.5 shadow-popover data-[state=open]:animate-[fade-in_var(--duration-base)_var(--ease-standard)]"
            >
              <Icon className={cn("mt-0.5 size-4 shrink-0", TONE[t.tone])} aria-hidden />
              <div className="min-w-0 flex-1">
                <T.Title className="text-sm font-medium text-ink">{t.title}</T.Title>
                {t.description ? (
                  <T.Description className="mt-0.5 text-[13px] text-ink-secondary">{t.description}</T.Description>
                ) : null}
              </div>
              <T.Close aria-label="Dismiss" className="rounded-[6px] p-0.5 text-ink-muted hover:bg-sunken hover:text-ink">
                <X className="size-4" aria-hidden />
              </T.Close>
            </T.Root>
          );
        })}
        <T.Viewport className="fixed right-4 bottom-4 z-[70] flex w-[min(380px,calc(100vw-32px))] flex-col gap-2 outline-none" />
      </T.Provider>
    </ToastContext.Provider>
  );
}

export function useToast() {
  return useContext(ToastContext);
}
