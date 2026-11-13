"use client";

import { BookOpen, KeyRound, Keyboard, LogOut, Menu, Search, UserRound } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";

import { AssistantLauncher } from "@/components/domain/agents/assistant-panel";
import { HelpIcon, NotificationsIcon } from "@/components/icons";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Kbd } from "@/components/ui/kbd";
import { Tooltip } from "@/components/ui/tooltip";
import { useMarkNotifications, useNotifications } from "@/features/notifications/use-notifications";
import type { Workspace } from "@/features/workspace/workspace";
import { useWorkspace } from "@/features/workspace/workspace-context";
import { formatRelative } from "@/lib/format";
import { cn } from "@/lib/cn";

export function Header({
  workspace,
  pageTitle,
  onOpenNav,
  onOpenCommand,
  onOpenShortcuts,
}: {
  workspace: Workspace;
  pageTitle: string;
  onOpenNav: () => void;
  onOpenCommand: () => void;
  onOpenShortcuts: () => void;
}) {
  return (
    <header className="sticky top-0 z-30 flex h-16 items-center gap-3 border-b border-line bg-canvas/95 px-4 backdrop-blur-sm md:px-6 lg:px-8">
      <Button variant="quiet" size="icon" className="lg:hidden" onClick={onOpenNav} aria-label="Open navigation">
        <Menu className="size-5" aria-hidden />
      </Button>

      <nav aria-label="Breadcrumb" className="min-w-0 flex-1">
        <ol className="flex items-center gap-1.5 text-sm">
          <li className="hidden truncate text-ink-muted sm:block">{workspace.organisation.name}</li>
          <li aria-hidden className="hidden text-line-control sm:block">/</li>
          <li aria-current="page" className="truncate font-medium text-ink">
            {pageTitle}
          </li>
        </ol>
      </nav>

      <button
        type="button"
        onClick={onOpenCommand}
        className="hidden h-9 w-64 items-center gap-2 rounded-control border border-line bg-raised px-3 text-sm text-ink-muted hover:border-line-control md:flex"
        aria-keyshortcuts="Control+K Meta+K"
      >
        <Search className="size-4 text-icon" aria-hidden />
        <span className="flex-1 text-left">Search</span>
        <Kbd>⌘K</Kbd>
      </button>
      <Button variant="quiet" size="icon" className="md:hidden" onClick={onOpenCommand} aria-label="Search">
        <Search className="size-[18px]" aria-hidden />
      </Button>

      <AssistantLauncher />

      <NotificationCentre />

      <DropdownMenu>
        <Tooltip content="Help">
          <DropdownMenuTrigger asChild>
            <Button variant="quiet" size="icon" aria-label="Help">
              <HelpIcon className="size-[18px]" strokeWidth={1.75} aria-hidden />
            </Button>
          </DropdownMenuTrigger>
        </Tooltip>
        <DropdownMenuContent>
          <DropdownMenuItem onSelect={onOpenShortcuts}>
            <Keyboard aria-hidden /> Keyboard shortcuts
          </DropdownMenuItem>
          <DropdownMenuItem asChild>
            <a href="/api/v1/docs" target="_blank" rel="noreferrer">
              <BookOpen aria-hidden /> API reference
            </a>
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>

      <DropdownMenu>
          <DropdownMenuTrigger
            className="inline-flex size-9 items-center justify-center rounded-full bg-ocean text-xs font-semibold text-white hover:bg-harbour"
            aria-label={`Account: ${workspace.user.name}`}
          >
            {workspace.user.initials}
          </DropdownMenuTrigger>
          <DropdownMenuContent className="w-64">
            <div className="px-2 py-2">
              <p className="text-sm font-medium text-ink">{workspace.user.name}</p>
              <p className="text-xs text-ink-muted">{workspace.user.role}</p>
              <p className="mt-0.5 font-mono text-[11px] text-ink-muted">{workspace.user.email}</p>
            </div>
            <DropdownMenuSeparator />
            <DropdownMenuItem asChild>
              <Link href="/account/profile">
                <UserRound aria-hidden /> Profile
              </Link>
            </DropdownMenuItem>
            <DropdownMenuItem asChild>
              <Link href="/account/security">
                <KeyRound aria-hidden /> Security
                {workspace.user.mfaEnabled ? null : <span className="ml-auto text-xs text-warning">2FA off</span>}
              </Link>
            </DropdownMenuItem>
            <DropdownMenuItem onSelect={onOpenShortcuts}>
              <Keyboard aria-hidden /> Keyboard shortcuts
            </DropdownMenuItem>
            <DropdownMenuSeparator />
            <SignOutItem />
          </DropdownMenuContent>
        </DropdownMenu>
    </header>
  );
}

function SignOutItem() {
  const { actions } = useWorkspace();
  return (
    <DropdownMenuItem onSelect={() => void actions.signOut()}>
      <LogOut aria-hidden /> Sign out
    </DropdownMenuItem>
  );
}

function NotificationCentre() {
  const router = useRouter();
  const { data } = useNotifications();
  const { markRead, markAllRead } = useMarkNotifications();
  const items = data?.items ?? [];
  const unread = data?.unread_count ?? 0;
  return (
    <DropdownMenu>
      <Tooltip content="Notifications">
        <DropdownMenuTrigger asChild>
          <Button
            variant="quiet"
            size="icon"
            className="relative"
            aria-label={unread ? `Notifications, ${unread} unread` : "Notifications"}
          >
            <NotificationsIcon className="size-[18px]" strokeWidth={1.75} aria-hidden />
            {unread ? (
              <span
                aria-hidden
                className="absolute top-1.5 right-1.5 inline-flex min-w-4 items-center justify-center rounded-full bg-danger px-1 text-[10px] leading-4 font-semibold text-white tnum"
              >
                {unread > 9 ? "9+" : unread}
              </span>
            ) : null}
          </Button>
        </DropdownMenuTrigger>
      </Tooltip>
      <DropdownMenuContent className="w-[min(380px,calc(100vw-32px))] p-0">
        <div className="flex items-center justify-between px-3 pt-3 pb-1">
          <DropdownMenuLabel className="p-0">Notifications</DropdownMenuLabel>
          {unread ? (
            <button
              type="button"
              onClick={() => markAllRead.mutate()}
              className="rounded-[6px] px-1.5 py-0.5 text-xs text-ink-secondary hover:bg-sunken hover:text-ink"
            >
              Mark all as read
            </button>
          ) : null}
        </div>
        {items.length === 0 ? (
          <p className="px-3 pt-1 pb-4 text-sm text-ink-muted">No notifications in this organisation yet.</p>
        ) : (
          <div className="max-h-[420px] overflow-y-auto p-1">
            {items.map((n) => {
              const isUnread = !n.read_at;
              return (
                <DropdownMenuItem
                  key={n.id}
                  className="items-start py-2"
                  onSelect={() => {
                    if (isUnread) markRead.mutate(n.id);
                    if (n.link) router.push(n.link);
                  }}
                >
                  <span
                    aria-hidden
                    className={cn("mt-1.5 size-1.5 shrink-0 rounded-full", isUnread ? "bg-ocean" : "bg-transparent")}
                  />
                  <span className="min-w-0 flex-1">
                    <span className={cn("block text-[13px] text-ink", isUnread && "font-medium")}>
                      {n.title}
                      {isUnread ? <span className="sr-only"> (unread)</span> : null}
                    </span>
                    {n.body ? <span className="block text-xs text-ink-muted">{n.body}</span> : null}
                  </span>
                  <span className="shrink-0 text-[11px] text-ink-muted tnum">{formatRelative(n.created_at)}</span>
                </DropdownMenuItem>
              );
            })}
          </div>
        )}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
