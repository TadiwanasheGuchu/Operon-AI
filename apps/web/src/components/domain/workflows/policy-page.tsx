"use client";

import { ArrowLeft, Plus, Trash2 } from "lucide-react";
import Link from "next/link";
import { useState } from "react";

import { ErrorState, PermissionDenied } from "@/components/feedback/states";
import { useToast } from "@/components/feedback/toast";
import { PageContainer, PageHeader } from "@/components/layout/page-header";
import { Button } from "@/components/ui/button";
import { Field, Input, Switch } from "@/components/ui/form";
import { Panel, PanelBody, PanelHeader } from "@/components/ui/panel";
import { Skeleton } from "@/components/ui/skeleton";
import {
  type PurchaseRequestParams,
  type WorkflowConfig,
  useWorkflowConfig,
  useWorkflowMutation,
} from "@/features/workflows/api";
import { useWorkspace } from "@/features/workspace/workspace-context";
import { api, ApiRequestError, errorMessage } from "@/lib/api/client";
import { formatDateTime } from "@/lib/format";

const APPROVER_ROLES = ["owner", "administrator", "operations_manager", "approver"] as const;

export function PolicyPage() {
  const { workspace } = useWorkspace();
  const config = useWorkflowConfig();
  if (!workspace.can("workflows.read")) {
    return (
      <PageContainer>
        <PermissionDenied permission="workflows.read" />
      </PageContainer>
    );
  }
  return (
    <PageContainer narrow>
      <Link href="/workflows" className="inline-flex items-center gap-1 text-[13px] text-ink-secondary hover:text-ink">
        <ArrowLeft className="size-4" aria-hidden /> Purchase requests
      </Link>
      <div className="mt-3">
        <PageHeader
          title="Approval policy"
          description="Who approves purchase requests, from what value, and how long they have. Saving creates a new version; requests already in progress keep the version they started with."
        />
      </div>
      {config.isPending ? (
        <Skeleton className="mt-6 h-96 w-full" />
      ) : config.isError ? (
        <ErrorState compact onRetry={() => config.refetch()} />
      ) : (
        <PolicyForm key={config.data.current_version} config={config.data} canManage={workspace.can("workflows.manage")} />
      )}
    </PageContainer>
  );
}

function PolicyForm({ config, canManage }: { config: WorkflowConfig; canManage: boolean }) {
  const toast = useToast();
  const [enabled, setEnabled] = useState(config.enabled);
  const [p, setP] = useState<PurchaseRequestParams>(config.params);
  const [errors, setErrors] = useState<string[]>([]);
  const save = useWorkflowMutation(() => api.put<WorkflowConfig>("/workflows/purchase-requests", { enabled, params: p }));
  const roleName = (r: string) => config.role_names[r] ?? r;
  const setStage = (i: number, patch: Partial<PurchaseRequestParams["stages"][number]>) =>
    setP((s) => ({ ...s, stages: s.stages.map((st, n) => (n === i ? { ...st, ...patch } : st)) }));
  const disabled = !canManage;
  return (
    <form
      className="mt-6 space-y-5"
      onSubmit={(e) => {
        e.preventDefault();
        setErrors([]);
        save.mutate(undefined, {
          onSuccess: (c) => toast({ tone: "success", title: `Policy saved as version ${c.current_version}` }),
          onError: (err) => {
            if (err instanceof ApiRequestError && err.code === "invalid_params") {
              const list = (err.details as { errors?: { field: string; message: string }[] }).errors ?? [];
              setErrors(list.map((x) => x.message.replace(/^Value error, /, "")));
            }
            toast({ tone: "danger", title: "Not saved", description: errorMessage(err) });
          },
        });
      }}
    >
      <Panel aria-labelledby="general-title">
        <PanelHeader
          id="general-title"
          title="General"
          actions={
            <div className="flex items-center gap-2">
              <span id="wf-enabled" className="text-xs text-ink-muted">
                {enabled ? "Requests on" : "Requests off"}
              </span>
              <Switch checked={enabled} onCheckedChange={setEnabled} disabled={disabled} aria-labelledby="general-title wf-enabled" />
            </div>
          }
        />
        <PanelBody className="grid gap-4 sm:grid-cols-3">
          <Field label="Policy currency" hint="Thresholds are in this currency. Requests in another currency need every stage.">
            {(f) => (
              <Input {...f} value={p.currency} maxLength={3} disabled={disabled} onChange={(e) => setP({ ...p, currency: e.target.value.toUpperCase() })} />
            )}
          </Field>
          <Field label="Time to decide (hours)" hint="Then approvers are reminded once; after that the request expires.">
            {(f) => (
              <Input {...f} type="number" min={1} max={720} value={p.approval_timeout_hours} disabled={disabled} onChange={(e) => setP({ ...p, approval_timeout_hours: Number(e.target.value) })} />
            )}
          </Field>
          <Field label="Send attempts" hint="Automatic retries if the purchasing system is unavailable.">
            {(f) => (
              <Input {...f} type="number" min={1} max={10} value={p.max_attempts} disabled={disabled} onChange={(e) => setP({ ...p, max_attempts: Number(e.target.value) })} />
            )}
          </Field>
        </PanelBody>
      </Panel>

      <Panel aria-labelledby="stages-title">
        <PanelHeader
          id="stages-title"
          title="Approval stages"
          description="Applied in order. The first stage applies to every request: an AI recommendation is never an approval."
        />
        <ol className="divide-y divide-line border-t border-line">
          {p.stages.map((st, i) => (
            <li key={i} className="space-y-4 px-5 py-4">
              <div className="grid gap-4 sm:grid-cols-2">
                <Field label={`Stage ${i + 1} name`}>
                  {(f) => <Input {...f} value={st.name} disabled={disabled} onChange={(e) => setStage(i, { name: e.target.value })} />}
                </Field>
                <Field label={`Applies from (${p.currency})`} hint={i === 0 ? "Always 0: every request needs this stage." : undefined}>
                  {(f) => (
                    <Input
                      {...f}
                      type="number"
                      min={0}
                      step="0.01"
                      value={st.min_value}
                      disabled={disabled || i === 0}
                      onChange={(e) => setStage(i, { min_value: e.target.value })}
                    />
                  )}
                </Field>
              </div>
              <fieldset>
                <legend className="text-[13px] font-medium text-ink">Who can approve</legend>
                <div className="mt-2 flex flex-wrap gap-x-5 gap-y-2">
                  {APPROVER_ROLES.map((r) => (
                    <label key={r} className="inline-flex items-center gap-2 text-sm text-ink">
                      <input
                        type="checkbox"
                        className="size-4 accent-[var(--color-primary)]"
                        checked={st.approver_roles.includes(r)}
                        disabled={disabled}
                        onChange={(e) =>
                          setStage(i, {
                            approver_roles: e.target.checked ? [...st.approver_roles, r] : st.approver_roles.filter((x) => x !== r),
                          })
                        }
                      />
                      {roleName(r)}
                    </label>
                  ))}
                </div>
              </fieldset>
              {i > 0 && !disabled ? (
                <Button type="button" variant="tertiary" size="sm" onClick={() => setP({ ...p, stages: p.stages.filter((_, n) => n !== i) })}>
                  <Trash2 aria-hidden /> Remove stage
                </Button>
              ) : null}
            </li>
          ))}
        </ol>
        {!disabled && p.stages.length < 5 ? (
          <div className="border-t border-line px-5 py-3">
            <Button
              type="button"
              variant="secondary"
              size="sm"
              onClick={() =>
                setP({
                  ...p,
                  stages: [
                    ...p.stages,
                    { name: "Additional approval", min_value: String(Number(p.stages.at(-1)?.min_value ?? 0) * 2 || 10000), approver_roles: ["owner"] },
                  ],
                })
              }
            >
              <Plus aria-hidden /> Add stage
            </Button>
          </div>
        ) : null}
      </Panel>

      {errors.length ? (
        <ul role="alert" className="list-disc space-y-1 pl-5 text-sm text-danger">
          {errors.map((m) => (
            <li key={m}>{m}</li>
          ))}
        </ul>
      ) : null}
      {canManage ? (
        <div className="flex gap-2">
          <Button type="submit" loading={save.isPending}>
            Save as version {config.current_version + 1}
          </Button>
          <Button
            type="button"
            variant="tertiary"
            onClick={() => {
              setP(config.params);
              setEnabled(config.enabled);
              setErrors([]);
            }}
          >
            Discard changes
          </Button>
        </div>
      ) : (
        <p className="text-xs text-ink-muted">You can view the policy. Changing it requires workflows.manage.</p>
      )}

      <Panel aria-labelledby="versions-title">
        <PanelHeader id="versions-title" title="Version history" />
        <ol className="space-y-2 px-5 pb-5">
          {config.versions.map((v) => (
            <li key={v.version} className="text-[13px] text-ink-secondary">
              <span className="font-medium text-ink">Version {v.version}</span>
              {v.version === config.current_version ? " (current)" : ""} · {formatDateTime(v.created_at)}
              {v.created_by ? ` by ${v.created_by.full_name}` : " (defaults)"} ·{" "}
              {v.params.stages.map((s) => `${s.name} from ${v.params.currency} ${Number(s.min_value).toLocaleString("en-GB")}`).join("; ")}
            </li>
          ))}
        </ol>
      </Panel>
    </form>
  );
}
