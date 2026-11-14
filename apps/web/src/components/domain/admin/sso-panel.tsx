"use client";

import { useQueryClient } from "@tanstack/react-query";
import { CircleCheck, Clock, Copy, Trash2 } from "lucide-react";
import { useState } from "react";

import { ConfirmDialog } from "@/components/feedback/confirm-dialog";
import { InlineAlert } from "@/components/feedback/inline-alert";
import { ErrorState } from "@/components/feedback/states";
import { useToast } from "@/components/feedback/toast";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Field, Input, Select } from "@/components/ui/form";
import { Panel, PanelBody, PanelHeader } from "@/components/ui/panel";
import { Skeleton } from "@/components/ui/skeleton";
import { type SsoDomain, type SsoRole, type SsoSettings, useSso } from "@/features/admin/governance";
import { useActiveOrganisation } from "@/features/session/use-session";
import { api, errorMessage } from "@/lib/api/client";

import { SwitchRow } from "./switch-row";

const ROLES: { key: SsoRole; label: string }[] = [
  { key: "viewer", label: "Viewer" },
  { key: "analyst", label: "Analyst" },
  { key: "approver", label: "Approver" },
  { key: "operations_manager", label: "Operations manager" },
];

function useRefreshSso() {
  const queryClient = useQueryClient();
  const org = useActiveOrganisation();
  return () => queryClient.invalidateQueries({ queryKey: ["tenant", org?.id, "sso"] });
}

export function SsoPanel({ canManage }: { canManage: boolean }) {
  const query = useSso();
  return (
    <Panel className="mt-5" aria-labelledby="org-sso">
      <PanelHeader
        id="org-sso"
        title="Single sign-on"
        description="Members with an email at a verified domain sign in through your identity provider (OpenID Connect)."
      />
      <PanelBody className="space-y-6">
        {query.isPending ? (
          <div className="space-y-3">
            <Skeleton className="h-10 w-full" />
            <Skeleton className="h-10 w-full" />
          </div>
        ) : query.isError ? (
          <ErrorState compact onRetry={() => query.refetch()} />
        ) : (
          <>
            <ConnectionForm key={JSON.stringify(query.data)} data={query.data} canManage={canManage} />
            {query.data.configured ? <Domains domains={query.data.domains} canManage={canManage} /> : null}
          </>
        )}
      </PanelBody>
    </Panel>
  );
}

function ConnectionForm({ data, canManage }: { data: SsoSettings; canManage: boolean }) {
  const toast = useToast();
  const refresh = useRefreshSso();
  const [issuer, setIssuer] = useState(data.issuer ?? "");
  const [clientId, setClientId] = useState(data.client_id ?? "");
  const [secret, setSecret] = useState("");
  const [enabled, setEnabled] = useState(data.enabled);
  const [enforce, setEnforce] = useState(data.enforce);
  const [jit, setJit] = useState(data.jit_provisioning);
  const [role, setRole] = useState<SsoRole>(data.default_role_key);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const hasVerified = data.domains.some((d) => d.verified);
  const missing = !issuer.trim() || !clientId.trim() || (!data.has_client_secret && !secret);

  return (
    <form
      noValidate
      className="space-y-4"
      onSubmit={async (e) => {
        e.preventDefault();
        setBusy(true);
        setError(null);
        try {
          await api.put("/organisations/current/sso", {
            issuer: issuer.trim(),
            client_id: clientId.trim(),
            client_secret: secret || null,
            enabled,
            enforce: enabled && enforce,
            jit_provisioning: jit,
            default_role_key: role,
          });
          setSecret("");
          await refresh();
          toast({ tone: "success", title: "Single sign-on saved" });
        } catch (err) {
          setError(err);
        } finally {
          setBusy(false);
        }
      }}
    >
      {error ? <InlineAlert tone="danger" title={errorMessage(error)} /> : null}
      <Field label="Redirect URI" hint="Register this address with your identity provider.">
        {(p) => (
          <div className="flex gap-2">
            <Input {...p} readOnly value={data.redirect_uri} className="font-mono text-[13px]" />
            <Button
              type="button"
              variant="secondary"
              aria-label="Copy redirect URI"
              onClick={async () => {
                try {
                  await navigator.clipboard.writeText(data.redirect_uri);
                  toast({ tone: "success", title: "Redirect URI copied" });
                } catch {
                  toast({ tone: "danger", title: "Couldn't copy. Select the text and copy it instead." });
                }
              }}
            >
              <Copy aria-hidden />
            </Button>
          </div>
        )}
      </Field>
      <Field label="Issuer URL" hint="For example https://login.example.com. It must serve OpenID Connect discovery.">
        {(p) => <Input {...p} type="url" value={issuer} disabled={!canManage} onChange={(e) => setIssuer(e.target.value)} />}
      </Field>
      <div className="grid gap-4 sm:grid-cols-2">
        <Field label="Client ID">
          {(p) => <Input {...p} value={clientId} disabled={!canManage} onChange={(e) => setClientId(e.target.value)} />}
        </Field>
        <Field
          label="Client secret"
          hint={data.has_client_secret ? "Saved and encrypted. Leave blank to keep it." : "Stored encrypted; never shown again."}
        >
          {(p) => (
            <Input
              {...p}
              type="password"
              autoComplete="off"
              value={secret}
              disabled={!canManage}
              placeholder={data.has_client_secret ? "••••••••" : ""}
              onChange={(e) => setSecret(e.target.value)}
            />
          )}
        </Field>
      </div>
      <SwitchRow
        label="Create accounts on first sign-in"
        hint="People at a verified domain join with the default role. Off: only invited members can sign in."
        checked={jit}
        onCheckedChange={setJit}
        disabled={!canManage}
      />
      <Field label="Default role for new members">
        {(p) => (
          <Select {...p} value={role} disabled={!canManage || !jit} onChange={(e) => setRole(e.target.value as SsoRole)}>
            {ROLES.map((r) => (
              <option key={r.key} value={r.key}>
                {r.label}
              </option>
            ))}
          </Select>
        )}
      </Field>
      <SwitchRow
        label="Turn on single sign-on"
        hint="Saving checks that the issuer responds before anyone is sent to it."
        checked={enabled}
        onCheckedChange={(v) => {
          setEnabled(v);
          if (!v) setEnforce(false);
        }}
        disabled={!canManage}
      />
      <SwitchRow
        label="Require single sign-on"
        hint={
          hasVerified
            ? "Members at verified domains can no longer use a password. Owners keep password sign-in as a break-glass."
            : "Verify an email domain first."
        }
        checked={enforce}
        onCheckedChange={setEnforce}
        disabled={!canManage || !enabled || !hasVerified}
      />
      {canManage ? (
        <Button type="submit" loading={busy} disabled={missing}>
          Save single sign-on
        </Button>
      ) : (
        <p className="text-xs text-ink-muted">Only owners and administrators can change single sign-on.</p>
      )}
    </form>
  );
}

function Domains({ domains, canManage }: { domains: SsoDomain[]; canManage: boolean }) {
  const toast = useToast();
  const refresh = useRefreshSso();
  const [domain, setDomain] = useState("");
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [removing, setRemoving] = useState<string | null>(null);

  return (
    <section aria-labelledby="sso-domains" className="space-y-3 border-t border-line pt-5">
      <h3 id="sso-domains" className="text-sm font-semibold text-ink">
        Email domains
      </h3>
      <p className="text-[13px] text-ink-muted">
        Prove you own each domain by publishing a DNS TXT record, then verify it. A domain can belong to one organisation.
      </p>
      {error ? <InlineAlert tone="danger" title={errorMessage(error)} /> : null}
      {domains.length === 0 ? <p className="text-[13px] text-ink-secondary">No domains yet.</p> : null}
      <ul className="space-y-3">
        {domains.map((d) => (
          <li key={d.domain} className="rounded-control border border-line p-3">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div className="flex items-center gap-2">
                <span className="font-mono text-[13px] text-ink">{d.domain}</span>
                {d.verified ? (
                  <Badge tone="success" icon={CircleCheck}>
                    Verified
                  </Badge>
                ) : (
                  <Badge tone="warning" icon={Clock}>
                    Not verified
                  </Badge>
                )}
              </div>
              {canManage ? (
                <div className="flex gap-2">
                  {!d.verified ? (
                    <Button
                      size="sm"
                      variant="secondary"
                      loading={busy === d.domain}
                      onClick={async () => {
                        setBusy(d.domain);
                        setError(null);
                        try {
                          await api.post(`/organisations/current/sso/domains/${encodeURIComponent(d.domain)}/verify`);
                          await refresh();
                          toast({ tone: "success", title: `${d.domain} verified` });
                        } catch (e) {
                          setError(e);
                        } finally {
                          setBusy(null);
                        }
                      }}
                    >
                      Verify
                    </Button>
                  ) : null}
                  <Button size="sm" variant="tertiary" aria-label={`Remove ${d.domain}`} onClick={() => setRemoving(d.domain)}>
                    <Trash2 aria-hidden />
                  </Button>
                </div>
              ) : null}
            </div>
            {!d.verified ? (
              <dl className="mt-2 grid gap-1 text-[13px] sm:grid-cols-[auto_1fr] sm:gap-x-3">
                <dt className="text-ink-muted">TXT name</dt>
                <dd className="break-all font-mono text-ink">{d.txt_name}</dd>
                <dt className="text-ink-muted">TXT value</dt>
                <dd className="break-all font-mono text-ink">{d.txt_value}</dd>
              </dl>
            ) : null}
          </li>
        ))}
      </ul>
      {canManage ? (
        <form
          noValidate
          className="flex items-end gap-2"
          onSubmit={async (e) => {
            e.preventDefault();
            setBusy("__add");
            setError(null);
            try {
              await api.post("/organisations/current/sso/domains", { domain: domain.trim() });
              setDomain("");
              await refresh();
            } catch (err) {
              setError(err);
            } finally {
              setBusy(null);
            }
          }}
        >
          <Field label="Add a domain" className="flex-1">
            {(p) => <Input {...p} placeholder="example.com" value={domain} onChange={(e) => setDomain(e.target.value)} />}
          </Field>
          <Button type="submit" variant="secondary" loading={busy === "__add"} disabled={domain.trim().length < 3}>
            Add
          </Button>
        </form>
      ) : null}
      <ConfirmDialog
        open={removing !== null}
        onOpenChange={(o) => !o && setRemoving(null)}
        title={`Remove ${removing ?? ""}?`}
        description="People at this domain can no longer use single sign-on for this organisation. If sign-on is required, they will need a password again."
        confirmLabel="Remove domain"
        destructive
        onConfirm={async () => {
          if (!removing) return;
          try {
            await api.delete(`/organisations/current/sso/domains/${encodeURIComponent(removing)}`);
            await refresh();
            toast({ tone: "success", title: `${removing} removed` });
          } catch (e) {
            toast({ tone: "danger", title: "Domain not removed", description: errorMessage(e) });
          }
          setRemoving(null);
        }}
      />
    </section>
  );
}
