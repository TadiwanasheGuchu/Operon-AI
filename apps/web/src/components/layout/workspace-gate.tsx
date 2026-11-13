"use client";

import { useQueryClient } from "@tanstack/react-query";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useMemo } from "react";

import { OperonMark } from "@/components/brand/operon-mark";
import { CreateOrganisationScreen } from "@/components/domain/admin/create-organisation";
import { setActiveOrganisationId } from "@/features/session/active-organisation";
import {
  useActiveOrganisation,
  useCurrentOrganisation,
  useSession,
  useSwitchOrganisation,
} from "@/features/session/use-session";
import type { Permission } from "@/features/session/types";
import { initials, type Workspace } from "@/features/workspace/workspace";
import { WorkspaceProvider, type WorkspaceActions } from "@/features/workspace/workspace-context";
import { api } from "@/lib/api/client";

import { AppShell } from "./app-shell";

export function WorkspaceGate({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const pathname = usePathname();
  const queryClient = useQueryClient();
  const session = useSession();
  const active = useActiveOrganisation();
  const current = useCurrentOrganisation();
  const switchOrganisation = useSwitchOrganisation();
  const user = session.data?.user ?? null;

  useEffect(() => {
    if (session.data && !user) router.replace(`/login?next=${encodeURIComponent(pathname)}`);
  }, [session.data, user, router, pathname]);

  const workspace = useMemo<Workspace | null>(() => {
    if (!user || !active) return null;
    const perms = new Set(current.data?.permissions ?? []);
    const orgs = (session.data?.organisations ?? []).map((o) => ({
      id: o.id,
      name: o.name,
      initials: initials(o.name),
      roleName: o.role_name,
      isDemo: o.is_demo,
    }));
    return {
      organisation: orgs.find((o) => o.id === active.id) ?? orgs[0],
      organisations: orgs,
      user: {
        name: user.full_name,
        initials: initials(user.full_name),
        role: active.role_name,
        email: user.email,
        mfaEnabled: user.mfa_enabled,
      },
      can: (p: Permission) => perms.has(p),
    };
  }, [user, active, current.data, session.data]);

  const actions = useMemo<WorkspaceActions>(
    () => ({
      switchOrganisation: (id) => {
        switchOrganisation(id);
        router.push("/overview");
      },
      signOut: async () => {
        await api.post("/auth/logout", undefined, { tenant: false }).catch(() => null);
        setActiveOrganisationId(null);
        queryClient.clear();
        router.replace("/login");
      },
    }),
    [switchOrganisation, router, queryClient],
  );

  if (session.isError) return <FullPageMessage title="Operon can't be reached right now" body="Check your connection and reload the page." />;
  if (session.isPending || !user) return <FullPageLoading />;
  if ((session.data?.organisations ?? []).length === 0) return <CreateOrganisationScreen first />;
  if (!workspace) return <FullPageLoading />;

  return (
    <WorkspaceProvider value={{ workspace, actions }}>
      <AppShell workspace={workspace}>{children}</AppShell>
    </WorkspaceProvider>
  );
}

function FullPageLoading() {
  return (
    <div role="status" aria-label="Loading your workspace" className="flex min-h-dvh items-center justify-center bg-canvas">
      <OperonMark className="size-8 animate-pulse text-ocean motion-reduce:animate-none" accent="var(--color-sky)" />
    </div>
  );
}

function FullPageMessage({ title, body }: { title: string; body: string }) {
  return (
    <div role="alert" className="flex min-h-dvh flex-col items-center justify-center gap-2 bg-canvas px-4 text-center">
      <OperonMark className="mb-2 size-8 text-ocean" accent="var(--color-sky)" />
      <h1 className="text-base font-semibold text-ink">{title}</h1>
      <p className="text-sm text-ink-muted">{body}</p>
    </div>
  );
}
