"use client";

import { CornerDownLeft, Search } from "lucide-react";
import { useRouter } from "next/navigation";
import { useId, useMemo, useRef, useState } from "react";

import { visibleModules, type Visibility } from "@/components/navigation/registry";
import { UsersIcon } from "@/components/icons";
import { useMembers } from "@/features/admin/api";
import { Dialog, DialogContent, DialogDescription, DialogTitle } from "@/components/ui/dialog";
import { Kbd } from "@/components/ui/kbd";
import { cn } from "@/lib/cn";

interface Command {
  id: string;
  label: string;
  section: string;
  icon: React.ComponentType<{ className?: string }>;
  href: string;
  keywords?: string;
}

function buildCommands(visibility: Visibility): Command[] {
  const nav = visibleModules(visibility).map((m) => ({
    id: `nav-${m.id}`,
    label: m.label,
    section: "Go to",
    icon: m.icon,
    href: m.href,
  }));
  return nav;
}

/** Keyboard-first launcher (⌘K / Ctrl+K). Only lists destinations that exist. */
export function CommandLauncher({
  open,
  onOpenChange,
  visibility,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  visibility: Visibility;
}) {
  const router = useRouter();
  const [query, setQuery] = useState("");
  const [active, setActive] = useState(0);
  const listId = useId();
  const inputRef = useRef<HTMLInputElement>(null);
  const commands = useMemo(() => buildCommands(visibility), [visibility]);
  const canSeePeople = visibility.can("members.read");
  const members = useMembers(canSeePeople && open);

  const results = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return commands;
    const pages = commands.filter((c) => `${c.label} ${c.section} ${c.keywords ?? ""}`.toLowerCase().includes(q));
    // Records search: people in this organisation (more record types join as modules ship).
    const people: Command[] =
      canSeePeople && members.data
        ? members.data
            .filter((m) => `${m.full_name} ${m.email} ${m.role_name}`.toLowerCase().includes(q))
            .slice(0, 6)
            .map((m) => ({
              id: `person-${m.id}`,
              label: `${m.full_name} · ${m.role_name}`,
              section: "People",
              icon: UsersIcon,
              href: "/admin/members",
              keywords: m.email,
            }))
        : [];
    return [...pages, ...people];
  }, [commands, query, canSeePeople, members.data]);

  function handleOpenChange(next: boolean) {
    if (!next) {
      setQuery("");
      setActive(0);
    }
    onOpenChange(next);
  }

  function run(command: Command | undefined) {
    if (!command) return;
    handleOpenChange(false);
    router.push(command.href);
  }

  function onKeyDown(event: React.KeyboardEvent) {
    if (event.key === "ArrowDown") {
      event.preventDefault();
      setActive((i) => Math.min(i + 1, results.length - 1));
    } else if (event.key === "ArrowUp") {
      event.preventDefault();
      setActive((i) => Math.max(i - 1, 0));
    } else if (event.key === "Enter") {
      event.preventDefault();
      run(results[active]);
    }
  }

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogContent
        hideClose
        className="max-w-xl overflow-hidden p-0"
        onOpenAutoFocus={(e) => {
          e.preventDefault();
          inputRef.current?.focus();
        }}
      >
        <DialogTitle className="sr-only">Search and navigate</DialogTitle>
        <DialogDescription className="sr-only">
          Type to filter destinations. Use the arrow keys to choose and Enter to open.
        </DialogDescription>
        <div className="flex items-center gap-2.5 border-b border-line px-4">
          <Search className="size-4 text-icon" aria-hidden />
          <input
            ref={inputRef}
            value={query}
            onChange={(e) => {
              setQuery(e.target.value);
              setActive(0);
            }}
            onKeyDown={onKeyDown}
            placeholder={canSeePeople ? "Search pages and people…" : "Search pages…"}
            className="h-12 flex-1 bg-transparent text-sm text-ink outline-none placeholder:text-ink-muted"
            role="combobox"
            aria-expanded="true"
            aria-controls={listId}
            aria-activedescendant={results[active] ? `${listId}-${results[active].id}` : undefined}
            aria-label={canSeePeople ? "Search pages and people" : "Search pages"}
          />
          <Kbd>Esc</Kbd>
        </div>
        <ul id={listId} role="listbox" aria-label="Results" className="max-h-80 overflow-y-auto p-1.5">
          {results.length === 0 ? (
            <li className="px-3 py-6 text-center text-sm text-ink-muted" role="presentation">
              Nothing matches “{query}”.
            </li>
          ) : (
            results.map((c, i) => {
              const Icon = c.icon;
              const showSection = i === 0 || results[i - 1].section !== c.section;
              return (
                <li key={c.id} role="presentation">
                  {showSection ? (
                    <p className="px-2.5 pt-2 pb-1 text-[11px] font-medium tracking-wide text-ink-muted uppercase" aria-hidden>
                      {c.section}
                    </p>
                  ) : null}
                  <div
                    id={`${listId}-${c.id}`}
                    role="option"
                    aria-selected={i === active}
                    onMouseMove={() => setActive(i)}
                    onClick={() => run(c)}
                    className={cn(
                      "flex h-10 cursor-pointer items-center gap-3 rounded-control px-2.5 text-sm",
                      i === active ? "bg-selected text-ink" : "text-ink-secondary",
                    )}
                  >
                    <Icon className="size-4 text-icon" />
                    <span className="flex-1">{c.label}</span>
                    {i === active ? <CornerDownLeft className="size-3.5 text-ink-muted" aria-hidden /> : null}
                  </div>
                </li>
              );
            })
          )}
        </ul>
      </DialogContent>
    </Dialog>
  );
}
