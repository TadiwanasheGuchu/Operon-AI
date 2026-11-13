import type { LucideIcon } from "lucide-react";
import { KeyRound, UserRound } from "lucide-react";

import {
  AgentsIcon,
  ApprovalsIcon,
  AuditIcon,
  ComponentsIcon,
  IncidentsIcon,
  IntegrationsIcon,
  IntelligenceIcon,
  KnowledgeIcon,
  OrganisationIcon,
  OverviewIcon,
  ReportsIcon,
  SecurityIcon,
  UsersIcon,
  WorkflowsIcon,
} from "@/components/icons";
import type { Permission } from "@/features/session/types";

export interface NavModule {
  id: string;
  label: string;
  href: string;
  icon: LucideIcon;
  group: "operate" | "connect" | "admin" | "account" | "system";
  /** Roadmap phase in which the module ships (docs/product/mvp-implementation-plan.md). */
  phase: number;
  implemented: boolean;
  /** Required to see the entry. The API enforces it independently. */
  permission?: Permission;
  /** Only shown in demo/development builds. */
  internal?: boolean;
  /** Reachable from the account menu and command launcher, not the sidebar. */
  sidebar?: boolean;
}

/**
 * Every module of the product, in navigation order. Only implemented modules the user may
 * access are rendered: the sidebar never links to a page that doesn't exist (CLAUDE.md §11).
 */
export const NAV_MODULES: NavModule[] = [
  { id: "overview", label: "Overview", href: "/overview", icon: OverviewIcon, group: "operate", phase: 2, implemented: true },
  { id: "intelligence", label: "Intelligence", href: "/intelligence", icon: IntelligenceIcon, group: "operate", phase: 4, implemented: true, permission: "insights.read" },
  { id: "incidents", label: "Incidents", href: "/incidents", icon: IncidentsIcon, group: "operate", phase: 4, implemented: true, permission: "incidents.read" },
  { id: "approvals", label: "Approvals", href: "/approvals", icon: ApprovalsIcon, group: "operate", phase: 5, implemented: true, permission: "workflows.read" },
  { id: "workflows", label: "Purchase requests", href: "/workflows", icon: WorkflowsIcon, group: "operate", phase: 5, implemented: true, permission: "workflows.read" },
  { id: "agents", label: "AI agents", href: "/agents", icon: AgentsIcon, group: "operate", phase: 6, implemented: true, permission: "agents.read" },
  { id: "integrations", label: "Integrations", href: "/integrations", icon: IntegrationsIcon, group: "connect", phase: 3, implemented: true, permission: "integrations.read" },
  { id: "knowledge", label: "Knowledge centre", href: "/knowledge", icon: KnowledgeIcon, group: "connect", phase: 8, implemented: false },
  { id: "reports", label: "Reports", href: "/reports", icon: ReportsIcon, group: "admin", phase: 8, implemented: false },
  { id: "members", label: "Members", href: "/admin/members", icon: UsersIcon, group: "admin", phase: 1, implemented: true, permission: "members.read" },
  { id: "roles", label: "Roles", href: "/admin/roles", icon: SecurityIcon, group: "admin", phase: 1, implemented: true, permission: "roles.read" },
  { id: "audit", label: "Audit log", href: "/admin/audit", icon: AuditIcon, group: "admin", phase: 1, implemented: true, permission: "audit.read" },
  { id: "organisation", label: "Organisation", href: "/admin/organisation", icon: OrganisationIcon, group: "admin", phase: 1, implemented: true, permission: "organisation.read" },
  { id: "profile", label: "Profile", href: "/account/profile", icon: UserRound, group: "account", phase: 1, implemented: true, sidebar: false },
  { id: "security", label: "Security", href: "/account/security", icon: KeyRound, group: "account", phase: 1, implemented: true, sidebar: false },
  { id: "components", label: "Component states", href: "/system/components", icon: ComponentsIcon, group: "system", phase: 0, implemented: true, internal: true },
];

export const NAV_GROUP_LABELS: Record<NavModule["group"], string> = {
  operate: "Operate",
  connect: "Connect",
  admin: "Administration",
  account: "Account",
  system: "Design system",
};

export interface Visibility {
  showInternal: boolean;
  can: (permission: Permission) => boolean;
}

export function visibleModules({ showInternal, can }: Visibility): NavModule[] {
  return NAV_MODULES.filter(
    (m) => m.implemented && (showInternal || !m.internal) && (!m.permission || can(m.permission)),
  );
}

export function sidebarModules(v: Visibility): NavModule[] {
  return visibleModules(v).filter((m) => m.sidebar !== false);
}

export function groupModules(modules: NavModule[]) {
  const order: NavModule["group"][] = ["operate", "connect", "admin", "account", "system"];
  return order
    .map((group) => ({ group, label: NAV_GROUP_LABELS[group], items: modules.filter((m) => m.group === group) }))
    .filter((g) => g.items.length > 0);
}
