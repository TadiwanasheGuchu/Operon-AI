"use client";

import { Check, ChevronsUpDown, PanelLeftClose, PanelLeftOpen, Plus } from "lucide-react";
import { useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";

import { OperonMark, OperonWordmark } from "@/components/brand/operon-mark";
import { CreateOrganisationDialog } from "@/components/domain/admin/create-organisation";
import { groupModules, sidebarModules } from "@/components/navigation/registry";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Tooltip } from "@/components/ui/tooltip";
import type { Workspace } from "@/features/workspace/workspace";
import { useWorkspace } from "@/features/workspace/workspace-context";
import { cn } from "@/lib/cn";

import { PlatformStatus } from "./platform-status";

export function SidebarContent({
  workspace,
  collapsed = false,
  onToggleCollapsed,
  onNavigate,
}: {
  workspace: Workspace;
  collapsed?: boolean;
  onToggleCollapsed?: () => void;
  onNavigate?: () => void;
}) {
  const pathname = usePathname();
  const groups = groupModules(
    sidebarModules({
      showInternal: process.env.NODE_ENV !== "production",
      can: workspace.can,
    }),
  );

  return (
    <div className="flex h-full flex-col border-r border-line-nav bg-nav text-ink-nav">
      <div className={cn("flex h-16 shrink-0 items-center", collapsed ? "justify-center px-2" : "justify-between pr-3 pl-5")}>
        <Link href="/overview" onClick={onNavigate} className="rounded-control" aria-label="Operon — Overview">
          {collapsed ? <OperonMark className="text-deep-sea" accent="var(--color-sky)" /> : <OperonWordmark className="text-deep-sea" />}
        </Link>
        {onToggleCollapsed && !collapsed ? (
          <CollapseButton collapsed={collapsed} onClick={onToggleCollapsed} />
        ) : null}
      </div>

      <div className={cn("px-3 pb-3", collapsed && "px-2")}>
        <OrganisationSwitcher workspace={workspace} collapsed={collapsed} />
      </div>

      <nav aria-label="Main" className="flex-1 overflow-y-auto px-3 pb-4">
        {groups.map(({ group, label, items }) => (
          <div key={group} className="mt-4 first:mt-1">
            <p className={cn("px-2 pb-1.5 text-[11px] font-medium tracking-[0.06em] text-ink-nav-muted uppercase", collapsed && "sr-only")}>
              {label}
            </p>
            <ul className="space-y-0.5">
              {items.map((item) => {
                const active = pathname === item.href || pathname.startsWith(`${item.href}/`);
                const Icon = item.icon;
                const link = (
                  <Link
                    href={item.href}
                    onClick={onNavigate}
                    aria-current={active ? "page" : undefined}
                    className={cn(
                      "relative flex h-9 items-center gap-3 rounded-control px-2.5 text-sm transition-colors transition-standard",
                      collapsed && "justify-center px-0",
                      active
                        ? "bg-nav-active font-medium text-ink-nav-active"
                        : "text-ink-nav hover:bg-nav-hover hover:text-ink",
                    )}
                  >
                    {active ? (
                      <span aria-hidden className="absolute top-2 bottom-2 left-0 w-[2px] rounded-full bg-primary" />
                    ) : null}
                    <Icon className="size-[18px] shrink-0" strokeWidth={1.75} aria-hidden />
                    <span className={cn(collapsed && "sr-only")}>{item.label}</span>
                  </Link>
                );
                return (
                  <li key={item.id}>
                    {collapsed ? <Tooltip content={item.label} side="right">{link}</Tooltip> : link}
                  </li>
                );
              })}
            </ul>
          </div>
        ))}
      </nav>

      <div className={cn("space-y-3 border-t border-line-nav px-5 py-4", collapsed && "px-2")}>
        <PlatformStatus collapsed={collapsed} />
        {onToggleCollapsed && collapsed ? (
          <div className="flex justify-center">
            <CollapseButton collapsed={collapsed} onClick={onToggleCollapsed} />
          </div>
        ) : null}
      </div>
    </div>
  );
}

function CollapseButton({ collapsed, onClick }: { collapsed: boolean; onClick: () => void }) {
  const Icon = collapsed ? PanelLeftOpen : PanelLeftClose;
  const label = collapsed ? "Expand sidebar" : "Collapse sidebar";
  return (
    <Tooltip content={label} side="right">
      <button
        type="button"
        onClick={onClick}
        aria-label={label}
        className="inline-flex size-8 items-center justify-center rounded-control text-ink-nav-muted hover:bg-nav-hover hover:text-ink"
      >
        <Icon className="size-[18px]" strokeWidth={1.75} aria-hidden />
      </button>
    </Tooltip>
  );
}

function OrganisationSwitcher({ workspace, collapsed }: { workspace: Workspace; collapsed: boolean }) {
  const { organisation, organisations } = workspace;
  const { actions } = useWorkspace();
  const [creating, setCreating] = useState(false);
  return (
    <>
      <DropdownMenu>
        <DropdownMenuTrigger
          aria-label={`Organisation: ${organisation.name}. Switch organisation`}
          className={cn(
            "flex w-full items-center gap-2.5 rounded-control border border-line-nav p-1.5 text-left text-sm hover:bg-nav-hover",
            collapsed && "justify-center border-transparent",
          )}
        >
          <span className="inline-flex size-7 shrink-0 items-center justify-center rounded-[6px] bg-mist text-[11px] font-semibold text-ocean">
            {organisation.initials}
          </span>
          <span className={cn("min-w-0 flex-1", collapsed && "sr-only")}>
            <span className="block truncate font-medium text-ink">{organisation.name}</span>
            <span className="block truncate text-[11px] text-ink-nav-muted">
              {organisation.isDemo ? `Demo · ${organisation.roleName}` : organisation.roleName}
            </span>
          </span>
          {collapsed ? null : <ChevronsUpDown className="size-4 shrink-0 text-ink-nav-muted" aria-hidden />}
        </DropdownMenuTrigger>
        <DropdownMenuContent align="start" side={collapsed ? "right" : "bottom"} className="w-64">
          <DropdownMenuLabel>Organisations</DropdownMenuLabel>
          {organisations.map((o) => (
            <DropdownMenuItem
              key={o.id}
              aria-current={o.id === organisation.id ? "true" : undefined}
              onSelect={() => o.id !== organisation.id && actions.switchOrganisation(o.id)}
            >
              <span className="min-w-0 flex-1">
                <span className="block truncate">{o.name}</span>
                <span className="block text-xs text-ink-muted">
                  {o.isDemo ? `Demo · ${o.roleName}` : o.roleName}
                </span>
              </span>
              {o.id === organisation.id ? <Check aria-label="Current" /> : null}
            </DropdownMenuItem>
          ))}
          <DropdownMenuSeparator />
          <DropdownMenuItem onSelect={() => setCreating(true)}>
            <Plus aria-hidden /> Create organisation
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>
      <CreateOrganisationDialog open={creating} onOpenChange={setCreating} />
    </>
  );
}
