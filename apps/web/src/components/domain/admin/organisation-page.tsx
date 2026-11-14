"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";

import { InlineAlert } from "@/components/feedback/inline-alert";
import { ErrorState } from "@/components/feedback/states";
import { useToast } from "@/components/feedback/toast";
import { PageContainer, PageHeader } from "@/components/layout/page-header";
import { Button } from "@/components/ui/button";
import { Field, Input, Switch } from "@/components/ui/form";
import { Panel, PanelBody, PanelHeader } from "@/components/ui/panel";
import { Skeleton } from "@/components/ui/skeleton";
import { sessionKey, useCurrentOrganisation } from "@/features/session/use-session";
import { useWorkspace } from "@/features/workspace/workspace-context";
import { api, errorMessage } from "@/lib/api/client";
import { formatDate } from "@/lib/format";

import { ExportPanel, RetentionPanel } from "./data-governance";
import { SsoPanel } from "./sso-panel";

const schema = z.object({ name: z.string().trim().min(1, "Enter a name.").max(200) });

export function OrganisationPage() {
  const { workspace } = useWorkspace();
  const current = useCurrentOrganisation();
  const canManage = workspace.can("organisation.manage");

  return (
    <PageContainer narrow>
      <PageHeader title="Organisation" description="Name, security policy, single sign-on and data governance for this organisation." />
      {current.isPending ? (
        <Panel className="mt-6 space-y-3 p-5">
          <Skeleton className="h-4 w-40" />
          <Skeleton className="h-10 w-full" />
        </Panel>
      ) : current.isError ? (
        <Panel className="mt-6">
          <ErrorState compact onRetry={() => current.refetch()} />
        </Panel>
      ) : (
        <>
          <NameForm key={current.data.name} name={current.data.name} canManage={canManage} createdAt={current.data.created_at} />
          <MfaPolicy required={current.data.mfa_required} canManage={canManage} youHaveMfa={workspace.user?.mfaEnabled ?? false} />
          <SsoPanel canManage={canManage} />
          <RetentionPanel canManage={canManage} />
          <ExportPanel canManage={canManage} />
        </>
      )}
    </PageContainer>
  );
}

function useRefreshOrganisation() {
  const queryClient = useQueryClient();
  return () =>
    Promise.all([
      queryClient.invalidateQueries({ queryKey: sessionKey }),
      queryClient.invalidateQueries({ predicate: (q) => q.queryKey[0] === "tenant" }),
    ]);
}

function NameForm({ name, canManage, createdAt }: { name: string; canManage: boolean; createdAt: string }) {
  const toast = useToast();
  const refresh = useRefreshOrganisation();
  const [error, setError] = useState<unknown>(null);
  const form = useForm<z.infer<typeof schema>>({ resolver: zodResolver(schema), defaultValues: { name } });
  return (
    <Panel className="mt-6" aria-labelledby="org-details">
      <PanelHeader id="org-details" title="Details" description={`Created ${formatDate(createdAt)}`} />
      <PanelBody>
        <form
          noValidate
          className="space-y-4"
          onSubmit={form.handleSubmit(async (v) => {
            setError(null);
            try {
              await api.patch("/organisations/current", v);
              await refresh();
              toast({ tone: "success", title: "Organisation name saved" });
            } catch (e) {
              setError(e);
            }
          })}
        >
          {error ? <InlineAlert tone="danger" title={errorMessage(error)} /> : null}
          <Field
            label="Organisation name"
            hint={canManage ? undefined : "Only owners and administrators can change this."}
            error={form.formState.errors.name?.message}
          >
            {(p) => <Input {...p} {...form.register("name")} disabled={!canManage} />}
          </Field>
          {canManage ? (
            <Button type="submit" loading={form.formState.isSubmitting} disabled={!form.formState.isDirty}>
              Save changes
            </Button>
          ) : null}
        </form>
      </PanelBody>
    </Panel>
  );
}

function MfaPolicy({ required, canManage, youHaveMfa }: { required: boolean; canManage: boolean; youHaveMfa: boolean }) {
  const toast = useToast();
  const refresh = useRefreshOrganisation();
  const [busy, setBusy] = useState(false);
  const blocked = !required && !youHaveMfa;
  return (
    <Panel className="mt-5" aria-labelledby="org-security">
      <PanelHeader id="org-security" title="Security policy" />
      <PanelBody className="space-y-4">
        <div className="flex items-start justify-between gap-6">
          <div>
            <p id="mfa-policy-label" className="text-sm font-medium text-ink">
              Require two-factor authentication
            </p>
            <p id="mfa-policy-hint" className="mt-0.5 text-[13px] text-ink-muted">
              Members without it can still sign in, but can&apos;t open this organisation until they turn it on.
            </p>
          </div>
          <Switch
            checked={required}
            disabled={!canManage || busy || blocked}
            aria-labelledby="mfa-policy-label"
            aria-describedby="mfa-policy-hint"
            onCheckedChange={async (value) => {
              setBusy(true);
              try {
                await api.patch("/organisations/current", { mfa_required: value });
                await refresh();
                toast({ tone: "success", title: value ? "Two-factor authentication is now required" : "Two-factor requirement turned off" });
              } catch (e) {
                toast({ tone: "danger", title: "Policy not changed", description: errorMessage(e) });
              } finally {
                setBusy(false);
              }
            }}
          />
        </div>
        {canManage && blocked ? (
          <InlineAlert tone="info" title="Turn on two-factor authentication for yourself first">
            So the policy can&apos;t lock you out. <Link href="/account/security" className="underline">Set it up now</Link>.
          </InlineAlert>
        ) : null}
        {!canManage ? <p className="text-xs text-ink-muted">Only owners and administrators can change the security policy.</p> : null}
      </PanelBody>
    </Panel>
  );
}
