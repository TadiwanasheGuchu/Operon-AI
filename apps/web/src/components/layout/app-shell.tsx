"use client";

import { FlaskConical } from "lucide-react";
import { usePathname } from "next/navigation";
import { useCallback, useEffect, useMemo, useState, useSyncExternalStore } from "react";

import { NAV_MODULES } from "@/components/navigation/registry";
import { Dialog, DialogContent, DialogDescription, DialogTitle, DrawerContent } from "@/components/ui/dialog";
import { Kbd } from "@/components/ui/kbd";
import type { Workspace } from "@/features/workspace/workspace";
import { cn } from "@/lib/cn";

import { CommandLauncher } from "./command-launcher";
import { TenantAccessGuard } from "./tenant-access-guard";
import { Header } from "./header";
import { SidebarContent } from "./sidebar";

const COLLAPSE_KEY = "operon.sidebar.collapsed";
const COLLAPSE_EVENT = "operon:sidebar";

// Per-viewer preference in localStorage, read through useSyncExternalStore so the server
// render (expanded) and the client agree, and storage failures degrade to "expanded".
function readCollapsed(): boolean {
  try {
    return window.localStorage.getItem(COLLAPSE_KEY) === "1";
  } catch {
    return false;
  }
}

function writeCollapsed(value: boolean) {
  try {
    window.localStorage.setItem(COLLAPSE_KEY, value ? "1" : "0");
  } catch {
    /* storage unavailable */
  }
  window.dispatchEvent(new Event(COLLAPSE_EVENT));
}

function subscribeCollapsed(onChange: () => void) {
  window.addEventListener("storage", onChange);
  window.addEventListener(COLLAPSE_EVENT, onChange);
  return () => {
    window.removeEventListener("storage", onChange);
    window.removeEventListener(COLLAPSE_EVENT, onChange);
  };
}

export function AppShell({ workspace, children }: { workspace: Workspace; children: React.ReactNode }) {
  const pathname = usePathname();
  const collapsed = useSyncExternalStore(subscribeCollapsed, readCollapsed, () => false);
  const [navOpen, setNavOpen] = useState(false);
  const [commandOpen, setCommandOpen] = useState(false);
  const [shortcutsOpen, setShortcutsOpen] = useState(false);
  const visibility = useMemo(
    () => ({
      showInternal: process.env.NODE_ENV !== "production",
      can: workspace.can,
    }),
    [workspace],
  );

  const toggleCollapsed = useCallback(() => writeCollapsed(!readCollapsed()), []);

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      const target = e.target as HTMLElement | null;
      const typing = target?.closest("input, textarea, select, [contenteditable=true]");
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setCommandOpen((o) => !o);
      } else if (!typing && e.key === "/") {
        e.preventDefault();
        setCommandOpen(true);
      } else if (!typing && (e.metaKey || e.ctrlKey) && e.key === "\\") {
        e.preventDefault();
        toggleCollapsed();
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [toggleCollapsed]);

  const pageTitle = NAV_MODULES.find((m) => pathname.startsWith(m.href))?.label ?? "Operon";

  return (
    <div className="min-h-dvh bg-canvas">
      <a
        href="#main"
        className="fixed top-2 left-2 z-[60] -translate-y-20 rounded-control bg-deep-sea px-3 py-2 text-sm text-white focus:translate-y-0"
      >
        Skip to main content
      </a>

      <aside
        aria-label="Sidebar"
        className={cn(
          "fixed inset-y-0 left-0 z-40 hidden overflow-hidden transition-[width] duration-[var(--duration-panel)] ease-[var(--ease-standard)] lg:block",
          collapsed ? "w-[var(--sidebar-width-collapsed)]" : "w-[var(--sidebar-width)]",
        )}
      >
        <SidebarContent workspace={workspace} collapsed={collapsed} onToggleCollapsed={toggleCollapsed} />
      </aside>

      <Dialog open={navOpen} onOpenChange={setNavOpen}>
        <DrawerContent side="left" aria-describedby={undefined}>
          <DialogTitle className="sr-only">Navigation</DialogTitle>
          <SidebarContent workspace={workspace} onNavigate={() => setNavOpen(false)} />
        </DrawerContent>
      </Dialog>

      <div
        className={cn(
          "flex min-h-dvh flex-col transition-[padding] duration-[var(--duration-panel)] ease-[var(--ease-standard)]",
          collapsed ? "lg:pl-[var(--sidebar-width-collapsed)]" : "lg:pl-[var(--sidebar-width)]",
        )}
      >
        {workspace.organisation.isDemo ? (
          <div className="flex items-center justify-center gap-2 border-b border-info/15 bg-info-bg px-4 py-1.5 text-center text-xs text-info">
            <FlaskConical className="size-3.5 shrink-0" aria-hidden />
            <span>
              <strong className="font-semibold">Demo organisation.</strong> Operational figures here are
              fictional sample data. Members, settings and the audit log are real.
            </span>
          </div>
        ) : null}
        <Header
          workspace={workspace}
          pageTitle={pageTitle}
          onOpenNav={() => setNavOpen(true)}
          onOpenCommand={() => setCommandOpen(true)}
          onOpenShortcuts={() => setShortcutsOpen(true)}
        />
        <main id="main" tabIndex={-1} className="flex-1 outline-none">
          <TenantAccessGuard>{children}</TenantAccessGuard>
        </main>
      </div>

      <CommandLauncher open={commandOpen} onOpenChange={setCommandOpen} visibility={visibility} />
      <ShortcutsDialog open={shortcutsOpen} onOpenChange={setShortcutsOpen} />
    </div>
  );
}

const SHORTCUTS: [string[], string][] = [
  [["⌘", "K"], "Search and navigate"],
  [["/"], "Search and navigate"],
  [["⌘", "\\"], "Collapse or expand the sidebar"],
  [["Esc"], "Close dialogs and menus"],
];

function ShortcutsDialog({ open, onOpenChange }: { open: boolean; onOpenChange: (o: boolean) => void }) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="p-6">
        <DialogTitle className="text-base font-semibold">Keyboard shortcuts</DialogTitle>
        <DialogDescription className="mt-1 text-[13px] text-ink-muted">
          On Windows and Linux, use Ctrl instead of ⌘.
        </DialogDescription>
        <dl className="mt-4 divide-y divide-line">
          {SHORTCUTS.map(([keys, label]) => (
            <div key={label + keys.join()} className="flex items-center justify-between py-2.5 text-sm">
              <dt className="text-ink-secondary">{label}</dt>
              <dd className="flex gap-1">
                {keys.map((k) => (
                  <Kbd key={k}>{k}</Kbd>
                ))}
              </dd>
            </div>
          ))}
        </dl>
      </DialogContent>
    </Dialog>
  );
}
