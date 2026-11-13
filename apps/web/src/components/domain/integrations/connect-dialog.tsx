"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import { InlineAlert } from "@/components/feedback/inline-alert";
import { useToast } from "@/components/feedback/toast";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogTitle } from "@/components/ui/dialog";
import { Field, Input, Select } from "@/components/ui/form";
import { type CatalogueEntry, type Connection, useIntegrationMutation } from "@/features/integrations/api";
import { api, ApiRequestError, errorMessage } from "@/lib/api/client";

/**
 * Connect a system. The form is generated from the connector's declared fields; secrets are
 * write-only (never prefilled or shown again). The API tests the connection before saving.
 */
export function ConnectDialog({
  entry,
  open,
  onOpenChange,
}: {
  entry: CatalogueEntry | null;
  open: boolean;
  onOpenChange: (o: boolean) => void;
}) {
  const router = useRouter();
  const toast = useToast();
  const [values, setValues] = useState<Record<string, string>>({});
  const [error, setError] = useState<unknown>(null);
  const create = useIntegrationMutation((body: unknown) => api.post<Connection>("/integrations", body));

  if (!entry) return null;
  const name = values.__name ?? `${entry.name}`;
  const interval = values.__interval ?? "15";
  const missing = entry.fields.filter((f) => f.required && !values[f.name]?.trim()).map((f) => f.label);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!entry || missing.length) return;
    setError(null);
    const config: Record<string, string> = {};
    const secrets: Record<string, string> = {};
    for (const f of entry.fields) {
      const v = values[f.name]?.trim();
      if (!v) continue;
      (f.secret ? secrets : config)[f.name] = v;
    }
    try {
      const conn = await create.mutateAsync({
        connector: entry.key,
        name: name.trim() || entry.name,
        config,
        secrets,
        sync_interval_minutes: Number(interval),
      });
      toast({
        tone: "success",
        title: `${conn.name} connected`,
        description: entry.key === "csv" ? "Upload your first file to start." : "The first sync has started.",
      });
      onOpenChange(false);
      setValues({});
      router.push(`/integrations/${conn.id}`);
    } catch (err) {
      setError(err);
    }
  }

  return (
    <Dialog
      open={open}
      onOpenChange={(o) => {
        onOpenChange(o);
        if (!o) {
          setValues({});
          setError(null);
        }
      }}
    >
      <DialogContent className="max-h-[85vh] overflow-y-auto p-6">
        <DialogTitle className="text-base font-semibold text-ink">Connect {entry.name}</DialogTitle>
        <DialogDescription className="mt-1 mb-5 text-[13px] text-ink-muted">{entry.description}</DialogDescription>
        {!entry.verified_live ? (
          <InlineAlert tone="info" title="Not yet verified against a live system" className="mb-5">
            {entry.verification_note}
          </InlineAlert>
        ) : null}
        <form noValidate className="space-y-4" onSubmit={submit}>
          {error ? (
            <InlineAlert
              tone="danger"
              title={error instanceof ApiRequestError && error.code === "connection_failed" ? "Couldn't connect" : "Not saved"}
            >
              {errorMessage(error)}
            </InlineAlert>
          ) : null}
          <Field label="Name in Operon" hint="How this connection appears in Operon.">
            {(p) => <Input {...p} value={name} onChange={(e) => setValues((v) => ({ ...v, __name: e.target.value }))} />}
          </Field>
          {entry.fields.map((f) => (
            <Field key={f.name} label={`${f.label}${f.required ? "" : " (optional)"}`} hint={f.help ?? undefined}>
              {(p) =>
                f.choices ? (
                  <Select {...p} value={values[f.name] ?? f.choices[0]} onChange={(e) => setValues((v) => ({ ...v, [f.name]: e.target.value }))}>
                    {f.choices.map((c) => (
                      <option key={c} value={c}>
                        {c}
                      </option>
                    ))}
                  </Select>
                ) : (
                  <Input
                    {...p}
                    type={f.secret ? "password" : "text"}
                    autoComplete={f.secret ? "new-password" : "off"}
                    spellCheck={false}
                    value={values[f.name] ?? ""}
                    onChange={(e) => setValues((v) => ({ ...v, [f.name]: e.target.value }))}
                  />
                )
              }
            </Field>
          ))}
          {entry.key !== "csv" ? (
            <Field label="Sync every" hint="Changes also arrive instantly when the system sends webhooks.">
              {(p) => (
                <Select {...p} value={interval} onChange={(e) => setValues((v) => ({ ...v, __interval: e.target.value }))}>
                  {[5, 15, 30, 60, 240, 1440].map((m) => (
                    <option key={m} value={m}>
                      {m < 60 ? `${m} minutes` : m === 60 ? "hour" : m === 1440 ? "day" : `${m / 60} hours`}
                    </option>
                  ))}
                </Select>
              )}
            </Field>
          ) : null}
          <div className="flex items-center justify-end gap-2 pt-2">
            {missing.length ? <p className="mr-auto text-xs text-ink-muted">Required: {missing.join(", ")}</p> : null}
            <Button type="button" variant="secondary" onClick={() => onOpenChange(false)}>
              Cancel
            </Button>
            <Button type="submit" loading={create.isPending} disabled={missing.length > 0}>
              {entry.key === "csv" ? "Create import" : "Test and connect"}
            </Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  );
}
