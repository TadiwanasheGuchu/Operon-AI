"use client";

import { ArrowLeft, Sparkles } from "lucide-react";
import Link from "next/link";
import { useState } from "react";

import { ErrorState, PermissionDenied } from "@/components/feedback/states";
import { InlineAlert } from "@/components/feedback/inline-alert";
import { useToast } from "@/components/feedback/toast";
import { PageContainer, PageHeader } from "@/components/layout/page-header";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Field, Input, Select, Switch } from "@/components/ui/form";
import { Panel, PanelBody, PanelHeader } from "@/components/ui/panel";
import { Skeleton } from "@/components/ui/skeleton";
import {
  type AISettings,
  type Detector,
  type DetectorParam,
  useAISettings,
  useDetectors,
  useInsightMutation,
} from "@/features/intelligence/api";
import { useWorkspace } from "@/features/workspace/workspace-context";
import { api, ApiRequestError, errorMessage } from "@/lib/api/client";
import { formatNumber, formatRelative } from "@/lib/format";

const PARAM_LABEL: Record<string, string> = {
  service_level: "Service level",
  sales_window_days: "Sales history window (days)",
  review_period_days: "Review period (days)",
  default_lead_time_days: "Default lead time (days)",
  min_history_days: "Minimum history for normal confidence (days)",
  grace_days: "Grace period (days)",
  medium_after_days: "Medium after (days late)",
  high_after_days: "High after (days late)",
  critical_after_days: "Critical after (days late)",
};

const CHOICE_LABEL: Record<string, string> = { "0.90": "90%", "0.95": "95%", "0.975": "97.5%", "0.99": "99%" };

export function IntelligenceSettingsPage() {
  const { workspace } = useWorkspace();
  const detectors = useDetectors();
  if (!workspace.can("insights.read")) {
    return (
      <PageContainer>
        <PermissionDenied permission="insights.read" />
      </PageContainer>
    );
  }
  return (
    <PageContainer narrow>
      <Link href="/intelligence" className="inline-flex items-center gap-1 text-[13px] text-ink-secondary hover:text-ink">
        <ArrowLeft className="size-4" aria-hidden /> Intelligence
      </Link>
      <div className="mt-3">
        <PageHeader
          title="Detectors and AI"
          description="Tune when Operon raises insights, and whether a model may rewrite their explanations. Changes apply at the next detection run."
        />
      </div>
      <AIPanel />
      <h2 className="mt-8 text-[15px] font-semibold text-ink">Detectors</h2>
      {detectors.isPending ? (
        <Skeleton className="mt-3 h-64 w-full" />
      ) : detectors.isError ? (
        <ErrorState compact onRetry={() => detectors.refetch()} />
      ) : (
        <div className="mt-3 space-y-5">
          {detectors.data.map((d) => (
            <DetectorPanel key={d.rule_id} detector={d} canManage={workspace.can("insights.manage")} />
          ))}
        </div>
      )}
    </PageContainer>
  );
}

function DetectorPanel({ detector: d, canManage }: { detector: Detector; canManage: boolean }) {
  const toast = useToast();
  const initial = Object.fromEntries(d.params.map((p) => [p.name, String(p.value ?? "")]));
  const [values, setValues] = useState<Record<string, string>>(initial);
  const [enabled, setEnabled] = useState(d.enabled);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const save = useInsightMutation(() =>
    api.put<Detector>(`/intelligence/detectors/${d.rule_id}`, {
      enabled,
      params: Object.fromEntries(
        d.params.map((p) => [p.name, p.type === "integer" || p.type === "number" ? Number(values[p.name]) : values[p.name]]),
      ),
    }),
  );
  const dirty = enabled !== d.enabled || d.params.some((p) => values[p.name] !== initial[p.name]);
  return (
    <Panel aria-labelledby={`${d.rule_id}-title`}>
      <PanelHeader
        id={`${d.rule_id}-title`}
        title={d.name}
        description={d.description}
        actions={
          <div className="flex items-center gap-2">
            <span className="text-xs text-ink-muted" id={`${d.rule_id}-switch`}>
              {enabled ? "On" : "Off"}
            </span>
            <Switch checked={enabled} onCheckedChange={setEnabled} disabled={!canManage} aria-labelledby={`${d.rule_id}-title ${d.rule_id}-switch`} />
          </div>
        }
      />
      <PanelBody>
        <p className="font-mono text-[11px] text-ink-muted">
          {d.rule_id} v{d.version}
          {d.updated_at ? ` · settings changed ${formatRelative(d.updated_at)}` : " · default settings"}
        </p>
        {!enabled ? (
          <p className="mt-3 text-[13px] text-ink-secondary">Turning a detector off closes the insights it raised at the next run.</p>
        ) : null}
        <form
          className="mt-4 grid gap-4 sm:grid-cols-2"
          onSubmit={(e) => {
            e.preventDefault();
            setErrors({});
            save.mutate(undefined, {
              onSuccess: () => toast({ tone: "success", title: `${d.name} saved`, description: "Applies at the next detection run." }),
              onError: (err) => {
                if (err instanceof ApiRequestError && err.code === "invalid_params") {
                  const list = (err.details as { errors?: { field: string; message: string }[] }).errors ?? [];
                  setErrors(Object.fromEntries(list.map((x) => [x.field || "_", x.message])));
                }
                toast({ tone: "danger", title: "Not saved", description: errorMessage(err) });
              },
            });
          }}
        >
          {d.params.map((p) => (
            <ParamField
              key={p.name}
              param={p}
              value={values[p.name] ?? ""}
              error={errors[p.name]}
              disabled={!canManage}
              onChange={(v) => setValues((s) => ({ ...s, [p.name]: v }))}
            />
          ))}
          {errors._ ? <p className="text-xs font-medium text-danger sm:col-span-2">{errors._}</p> : null}
          {canManage ? (
            <div className="flex gap-2 sm:col-span-2">
              <Button type="submit" disabled={!dirty} loading={save.isPending}>
                Save
              </Button>
              <Button
                type="button"
                variant="tertiary"
                disabled={!dirty}
                onClick={() => {
                  setValues(initial);
                  setEnabled(d.enabled);
                  setErrors({});
                }}
              >
                Discard changes
              </Button>
            </div>
          ) : (
            <p className="text-xs text-ink-muted sm:col-span-2">You can view these settings. Changing them requires insights.manage.</p>
          )}
        </form>
      </PanelBody>
    </Panel>
  );
}

function ParamField({
  param: p,
  value,
  error,
  disabled,
  onChange,
}: {
  param: DetectorParam;
  value: string;
  error?: string;
  disabled: boolean;
  onChange: (v: string) => void;
}) {
  const range = p.minimum !== null && p.maximum !== null ? ` Between ${p.minimum} and ${p.maximum}.` : "";
  return (
    <Field label={PARAM_LABEL[p.name] ?? p.name} hint={`${p.description ?? ""}${range} Default ${CHOICE_LABEL[String(p.default)] ?? String(p.default)}.`} error={error}>
      {(props) =>
        p.choices ? (
          <Select {...props} value={value} disabled={disabled} onChange={(e) => onChange(e.target.value)}>
            {p.choices.map((c) => (
              <option key={c} value={c}>
                {CHOICE_LABEL[c] ?? c}
              </option>
            ))}
          </Select>
        ) : (
          <Input
            {...props}
            type="number"
            inputMode="numeric"
            min={p.minimum ?? undefined}
            max={p.maximum ?? undefined}
            value={value}
            disabled={disabled}
            onChange={(e) => onChange(e.target.value)}
          />
        )
      }
    </Field>
  );
}

function AIPanel() {
  const { workspace } = useWorkspace();
  const ai = useAISettings();
  return (
    <Panel className="mt-6" aria-labelledby="ai-title">
      <PanelHeader
        id="ai-title"
        title="AI-written explanations"
        description="Optional. Detection, numbers and recommendations never depend on a model; a model may only rephrase the explanation."
        actions={ai.data ? <Badge tone={ai.data.enabled ? "success" : "neutral"} icon={Sparkles}>{ai.data.enabled ? "On" : "Off"}</Badge> : undefined}
      />
      <PanelBody>
        {ai.isPending ? (
          <Skeleton className="h-24 w-full" />
        ) : ai.isError ? (
          <ErrorState compact onRetry={() => ai.refetch()} />
        ) : (
          <AIForm settings={ai.data} canManage={workspace.can("organisation.manage")} />
        )}
      </PanelBody>
    </Panel>
  );
}

function AIForm({ settings: s, canManage }: { settings: AISettings; canManage: boolean }) {
  const toast = useToast();
  const [enabled, setEnabled] = useState(s.enabled);
  const [provider, setProvider] = useState(s.provider);
  const [budget, setBudget] = useState(String(s.monthly_token_budget));
  const save = useInsightMutation(() =>
    api.put<AISettings>("/intelligence/ai-settings", { enabled, provider, monthly_token_budget: Number(budget) }),
  );
  const none = s.available_providers.length === 0;
  return (
    <div className="space-y-4">
      <p className="text-[13px] text-ink-secondary">{s.data_shared}</p>
      {none ? (
        <InlineAlert tone="info" title="No model provider is configured on this deployment">
          Explanations are written from templates. A platform administrator can add an Anthropic or OpenAI key to the server
          environment; then you can turn this on.
        </InlineAlert>
      ) : null}
      <p className="text-xs text-ink-muted tnum">
        {formatNumber(s.tokens_used_this_month)} of {formatNumber(s.monthly_token_budget)} tokens used this month
        {s.model ? ` · model ${s.model}` : ""}
      </p>
      {canManage ? (
        <form
          className="grid gap-4 sm:grid-cols-3"
          onSubmit={(e) => {
            e.preventDefault();
            save.mutate(undefined, {
              onSuccess: () => toast({ tone: "success", title: "AI settings saved" }),
              onError: (err) => toast({ tone: "danger", title: "Not saved", description: errorMessage(err) }),
            });
          }}
        >
          <div className="flex items-center gap-3 sm:col-span-3">
            <Switch checked={enabled} onCheckedChange={setEnabled} disabled={none && !s.enabled} aria-labelledby="ai-enabled-label" />
            <span id="ai-enabled-label" className="text-sm text-ink">
              Let a model rewrite explanations
            </span>
          </div>
          <Field label="Provider">
            {(p) => (
              <Select {...p} value={provider} onChange={(e) => setProvider(e.target.value as AISettings["provider"])}>
                <option value="anthropic">Anthropic{s.available_providers.includes("anthropic") ? "" : " (not configured)"}</option>
                <option value="openai">OpenAI{s.available_providers.includes("openai") ? "" : " (not configured)"}</option>
              </Select>
            )}
          </Field>
          <Field label="Monthly token budget" hint="When spent, templates are used until next month.">
            {(p) => <Input {...p} type="number" min={0} value={budget} onChange={(e) => setBudget(e.target.value)} />}
          </Field>
          <div className="flex items-end">
            <Button type="submit" loading={save.isPending}>
              Save
            </Button>
          </div>
        </form>
      ) : (
        <p className="text-xs text-ink-muted">Changing these settings requires organisation.manage.</p>
      )}
    </div>
  );
}
