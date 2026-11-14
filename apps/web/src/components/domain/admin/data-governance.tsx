"use client";

import { useQueryClient } from "@tanstack/react-query";
import { Download } from "lucide-react";
import { useState } from "react";

import { InlineAlert } from "@/components/feedback/inline-alert";
import { ErrorState } from "@/components/feedback/states";
import { useToast } from "@/components/feedback/toast";
import { Button } from "@/components/ui/button";
import { Field, Input } from "@/components/ui/form";
import { Panel, PanelBody, PanelHeader } from "@/components/ui/panel";
import { Skeleton } from "@/components/ui/skeleton";
import { downloadExport, type Retention, type RetentionKey, useRetention } from "@/features/admin/governance";
import { useActiveOrganisation } from "@/features/session/use-session";
import { api, errorMessage } from "@/lib/api/client";

const FIELDS: { key: RetentionKey; label: string; hint: string }[] = [
  { key: "audit_days", label: "Audit log", hint: "Who did what, and when." },
  { key: "conversation_days", label: "Assistant conversations", hint: "Members' private questions and answers." },
  { key: "run_log_days", label: "Assistant and agent run logs", hint: "Model turns and tool calls behind each answer or run." },
  { key: "sync_job_days", label: "Integration sync history", hint: "One record per sync, with counts and errors." },
];

export function RetentionPanel({ canManage }: { canManage: boolean }) {
  const query = useRetention();
  return (
    <Panel className="mt-5" aria-labelledby="org-retention">
      <PanelHeader
        id="org-retention"
        title="Data retention"
        description="Older records are deleted automatically. Insights, incidents and purchase requests are kept."
      />
      <PanelBody>
        {query.isPending ? (
          <div className="space-y-3">
            <Skeleton className="h-10 w-full" />
            <Skeleton className="h-10 w-full" />
          </div>
        ) : query.isError ? (
          <ErrorState compact onRetry={() => query.refetch()} />
        ) : (
          <RetentionForm key={JSON.stringify(query.data)} data={query.data} canManage={canManage} />
        )}
      </PanelBody>
    </Panel>
  );
}

function RetentionForm({ data, canManage }: { data: Retention; canManage: boolean }) {
  const toast = useToast();
  const queryClient = useQueryClient();
  const org = useActiveOrganisation();
  const [values, setValues] = useState<Record<RetentionKey, string>>(
    () => Object.fromEntries(FIELDS.map((f) => [f.key, String(data[f.key])])) as Record<RetentionKey, string>,
  );
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);

  const problems = Object.fromEntries(
    FIELDS.map((f) => {
      const [min, max] = data.bounds[f.key];
      const n = Number(values[f.key]);
      return [f.key, Number.isInteger(n) && n >= min && n <= max ? undefined : `Enter whole days from ${min} to ${max}.`];
    }),
  ) as Record<RetentionKey, string | undefined>;
  const dirty = FIELDS.some((f) => Number(values[f.key]) !== data[f.key]);
  const valid = FIELDS.every((f) => !problems[f.key]);

  return (
    <form
      noValidate
      className="space-y-4"
      onSubmit={async (e) => {
        e.preventDefault();
        if (!valid) return;
        setBusy(true);
        setError(null);
        try {
          await api.put("/organisations/current/retention", Object.fromEntries(FIELDS.map((f) => [f.key, Number(values[f.key])])));
          await queryClient.invalidateQueries({ queryKey: ["tenant", org?.id, "retention"] });
          toast({ tone: "success", title: "Retention policy saved" });
        } catch (err) {
          setError(err);
        } finally {
          setBusy(false);
        }
      }}
    >
      {error ? <InlineAlert tone="danger" title={errorMessage(error)} /> : null}
      <div className="grid gap-4 sm:grid-cols-2">
        {FIELDS.map((f) => {
          const [min, max] = data.bounds[f.key];
          return (
            <Field key={f.key} label={`${f.label} (days)`} hint={`${f.hint} ${min}–${max} days.`} error={problems[f.key]}>
              {(p) => (
                <Input
                  {...p}
                  type="number"
                  inputMode="numeric"
                  min={min}
                  max={max}
                  value={values[f.key]}
                  disabled={!canManage}
                  onChange={(e) => setValues((v) => ({ ...v, [f.key]: e.target.value }))}
                />
              )}
            </Field>
          );
        })}
      </div>
      {canManage ? (
        <Button type="submit" loading={busy} disabled={!dirty || !valid}>
          Save retention policy
        </Button>
      ) : (
        <p className="text-xs text-ink-muted">Only owners and administrators can change retention.</p>
      )}
    </form>
  );
}

export function ExportPanel({ canManage }: { canManage: boolean }) {
  const toast = useToast();
  const [busy, setBusy] = useState(false);
  return (
    <Panel className="mt-5" aria-labelledby="org-export">
      <PanelHeader
        id="org-export"
        title="Export data"
        description="A ZIP of JSON Lines files, one per kind of record, with a manifest."
      />
      <PanelBody className="space-y-3">
        <p className="text-[13px] text-ink-secondary">
          Includes members, operational data, insights, incidents, workflows, agent runs and the audit log. Not included:
          integration credentials, passwords and two-factor secrets, invitation tokens, the single sign-on client secret, and
          members&apos; private assistant conversations. Each export is recorded in the audit log; up to five a day.
        </p>
        {canManage ? (
          <Button
            variant="secondary"
            loading={busy}
            onClick={async () => {
              setBusy(true);
              try {
                await downloadExport();
                toast({ tone: "success", title: "Export downloaded" });
              } catch (e) {
                toast({ tone: "danger", title: "Export failed", description: errorMessage(e) });
              } finally {
                setBusy(false);
              }
            }}
          >
            <Download aria-hidden /> Download export
          </Button>
        ) : (
          <p className="text-xs text-ink-muted">Only owners and administrators can export the organisation&apos;s data.</p>
        )}
      </PanelBody>
    </Panel>
  );
}
