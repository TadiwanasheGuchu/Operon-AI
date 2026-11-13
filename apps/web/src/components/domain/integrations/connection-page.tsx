"use client";

import { ArrowLeft, Copy, Download, PauseCircle, PlayCircle, RefreshCw, Upload } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useRef, useState } from "react";

import { Table, TableScroll, Td, Th, Tr } from "@/components/data-display/table";
import { ConfirmDialog } from "@/components/feedback/confirm-dialog";
import { InlineAlert } from "@/components/feedback/inline-alert";
import { EmptyState, ErrorState, PermissionDenied } from "@/components/feedback/states";
import { useToast } from "@/components/feedback/toast";
import { PageContainer } from "@/components/layout/page-header";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogTitle } from "@/components/ui/dialog";
import { Field, Input, Select } from "@/components/ui/form";
import { Panel, PanelBody, PanelHeader } from "@/components/ui/panel";
import { Skeleton } from "@/components/ui/skeleton";
import {
  type Connection,
  IMPORT_KINDS,
  type ImportKind,
  type SyncJob,
  type UploadResult,
  uploadCsv,
  useCatalogue,
  useConnection,
  useEvents,
  useIntegrationMutation,
  useSyncJobs,
} from "@/features/integrations/api";
import { useWorkspace } from "@/features/workspace/workspace-context";
import { api, ApiRequestError, errorMessage } from "@/lib/api/client";
import { formatDateTime, formatRelative } from "@/lib/format";

import { CONNECTOR_LABEL, ConnectionStatusBadge } from "./status";

export function ConnectionPage({ id }: { id: string }) {
  const { workspace } = useWorkspace();
  const canManage = workspace.can("integrations.manage");
  const conn = useConnection(id);

  if (!workspace.can("integrations.read")) {
    return (
      <PageContainer>
        <PermissionDenied permission="integrations.read" />
      </PageContainer>
    );
  }
  if (conn.isPending) {
    return (
      <PageContainer>
        <div role="status" aria-label="Loading connection" className="space-y-4">
          <Skeleton className="h-9 w-72 max-w-full" />
          <Skeleton className="h-40 w-full" />
        </div>
      </PageContainer>
    );
  }
  if (conn.isError) {
    const notFound = conn.error instanceof ApiRequestError && conn.error.status === 404;
    return (
      <PageContainer>
        <ErrorState
          title={notFound ? "This connection doesn't exist" : "The connection couldn't be loaded"}
          description={notFound ? "It may have been disconnected." : undefined}
          onRetry={notFound ? undefined : () => conn.refetch()}
        />
      </PageContainer>
    );
  }
  const c = conn.data;
  return (
    <PageContainer>
      <Link href="/integrations" className="inline-flex items-center gap-1 text-[13px] text-ink-secondary hover:text-ink">
        <ArrowLeft className="size-4" aria-hidden /> Integrations
      </Link>
      <Header connection={c} canManage={canManage} />
      {c.last_error ? (
        <InlineAlert
          className="mt-5"
          tone={c.status === "action_required" ? "danger" : "warning"}
          title={c.status === "action_required" ? "This connection needs attention" : "The last sync failed"}
          action={canManage && c.status === "action_required" && c.connector !== "csv" ? <RotateButton connection={c} /> : undefined}
        >
          {c.last_error}
        </InlineAlert>
      ) : null}
      <div className="mt-5 grid grid-cols-1 gap-5 xl:grid-cols-12">
        <div className="min-w-0 space-y-5 xl:col-span-8">
          {c.connector === "csv" && canManage ? <CsvUpload connection={c} /> : null}
          <SyncHistory connection={c} />
          {c.connector === "shopify" ? <Events connection={c} /> : null}
        </div>
        <div className="min-w-0 space-y-5 xl:col-span-4">
          <Settings connection={c} canManage={canManage} />
          {c.webhook_url ? <Webhook connection={c} /> : null}
        </div>
      </div>
    </PageContainer>
  );
}

function Header({ connection: c, canManage }: { connection: Connection; canManage: boolean }) {
  const toast = useToast();
  const router = useRouter();
  const [disconnecting, setDisconnecting] = useState(false);
  const sync = useIntegrationMutation(() => api.post(`/integrations/${c.id}/sync`));
  const pause = useIntegrationMutation((paused: boolean) => api.patch(`/integrations/${c.id}`, { paused }));
  const test = useIntegrationMutation(() =>
    api.post<{ ok: boolean; summary: string | null; message: string | null }>(`/integrations/${c.id}/test`),
  );
  const remove = useIntegrationMutation(() => api.delete(`/integrations/${c.id}`));
  const paused = c.status === "paused";

  return (
    <div className="mt-3 flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
      <div className="min-w-0">
        <p className="text-[13px] text-ink-muted">{CONNECTOR_LABEL[c.connector]}</p>
        <h1 className="mt-1 flex flex-wrap items-center gap-3 font-display text-[30px] leading-9 font-medium text-ink">
          {c.name} <ConnectionStatusBadge status={c.status} />
        </h1>
        <p className="mt-1.5 text-xs text-ink-muted">
          {c.last_success_at ? `Last successful sync ${formatRelative(c.last_success_at)}` : "Not synced yet"}
          {c.connector !== "csv" && !paused ? ` · every ${c.sync_interval_minutes} minutes` : ""}
        </p>
      </div>
      {canManage ? (
        <div className="flex flex-wrap gap-2">
          {c.connector !== "csv" ? (
            <>
              <Button
                variant="secondary"
                loading={test.isPending}
                onClick={() =>
                  test.mutate(undefined, {
                    onSuccess: (r) =>
                      r.ok
                        ? toast({ tone: "success", title: "Connection works", description: r.summary ?? undefined })
                        : toast({ tone: "danger", title: "Connection failed", description: r.message ?? undefined }),
                  })
                }
              >
                Test connection
              </Button>
              <Button
                variant="secondary"
                onClick={() =>
                  pause.mutate(!paused, {
                    onSuccess: () => toast({ tone: "info", title: paused ? "Syncing resumed" : "Syncing paused" }),
                    onError: (e) => toast({ tone: "danger", title: "Not changed", description: errorMessage(e) }),
                  })
                }
              >
                {paused ? <PlayCircle aria-hidden /> : <PauseCircle aria-hidden />}
                {paused ? "Resume" : "Pause"}
              </Button>
              <Button
                loading={sync.isPending}
                disabled={paused}
                onClick={() =>
                  sync.mutate(undefined, {
                    onSuccess: () => toast({ tone: "success", title: "Sync requested" }),
                    onError: (e) => toast({ tone: "danger", title: "Sync not started", description: errorMessage(e) }),
                  })
                }
              >
                <RefreshCw aria-hidden /> Sync now
              </Button>
            </>
          ) : null}
          <Button variant="tertiary" className="text-danger hover:text-danger" onClick={() => setDisconnecting(true)}>
            Disconnect
          </Button>
        </div>
      ) : null}
      <ConfirmDialog
        open={disconnecting}
        onOpenChange={setDisconnecting}
        destructive
        title={`Disconnect ${c.name}?`}
        description="Operon stops syncing and deletes the credentials and every record imported through this connection: locations, products, stock, sales and purchase orders. Data in the source system isn't touched. This can't be undone."
        confirmLabel="Disconnect and delete data"
        onConfirm={async () => {
          try {
            await remove.mutateAsync(undefined);
            toast({ tone: "success", title: `${c.name} disconnected` });
            router.push("/integrations");
          } catch (e) {
            toast({ tone: "danger", title: "Not disconnected", description: errorMessage(e) });
          }
        }}
      />
    </div>
  );
}

function RotateButton({ connection }: { connection: Connection }) {
  const [open, setOpen] = useState(false);
  return (
    <>
      <Button size="sm" variant="secondary" onClick={() => setOpen(true)}>
        Update credentials
      </Button>
      <RotateDialog connection={connection} open={open} onOpenChange={setOpen} />
    </>
  );
}

function RotateDialog({ connection: c, open, onOpenChange }: { connection: Connection; open: boolean; onOpenChange: (o: boolean) => void }) {
  const toast = useToast();
  const catalogue = useCatalogue();
  const fields = catalogue.data?.find((e) => e.key === c.connector)?.fields.filter((f) => f.secret) ?? [];
  const [values, setValues] = useState<Record<string, string>>({});
  const [error, setError] = useState<unknown>(null);
  const rotate = useIntegrationMutation((secrets: Record<string, string>) =>
    api.put(`/integrations/${c.id}/credentials`, { secrets }),
  );
  return (
    <Dialog open={open} onOpenChange={(o) => { onOpenChange(o); if (!o) { setValues({}); setError(null); } }}>
      <DialogContent className="p-6">
        <DialogTitle className="text-base font-semibold text-ink">Update credentials</DialogTitle>
        <DialogDescription className="mt-1 mb-5 text-[13px] text-ink-muted">
          Operon tests the new credentials before saving them, then runs a sync. Current values are never shown.
        </DialogDescription>
        <form
          className="space-y-4"
          noValidate
          onSubmit={async (e) => {
            e.preventDefault();
            setError(null);
            try {
              const secrets = Object.fromEntries(Object.entries(values).filter(([, v]) => v.trim()));
              await rotate.mutateAsync(secrets);
              toast({ tone: "success", title: "Credentials updated", description: "A sync is running with the new credentials." });
              onOpenChange(false);
            } catch (err) {
              setError(err);
            }
          }}
        >
          {error ? <InlineAlert tone="danger" title="Not saved">{errorMessage(error)}</InlineAlert> : null}
          {fields.map((f) => (
            <Field key={f.name} label={`${f.label}${f.required ? "" : " (optional)"}`} hint={f.help ?? undefined}>
              {(p) => (
                <Input {...p} type="password" autoComplete="new-password" value={values[f.name] ?? ""} onChange={(e) => setValues((v) => ({ ...v, [f.name]: e.target.value }))} />
              )}
            </Field>
          ))}
          <div className="flex justify-end gap-2 pt-1">
            <Button type="button" variant="secondary" onClick={() => onOpenChange(false)}>
              Cancel
            </Button>
            <Button type="submit" loading={rotate.isPending} disabled={!fields.filter((f) => f.required).every((f) => values[f.name]?.trim())}>
              Test and save
            </Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  );
}

function Settings({ connection: c, canManage }: { connection: Connection; canManage: boolean }) {
  const toast = useToast();
  const [rotating, setRotating] = useState(false);
  const update = useIntegrationMutation((minutes: number) => api.patch(`/integrations/${c.id}`, { sync_interval_minutes: minutes }));
  const config = Object.entries(c.config);
  return (
    <Panel aria-labelledby="settings-title">
      <PanelHeader id="settings-title" title="Settings" />
      <PanelBody className="space-y-4">
        {config.length ? (
          <dl className="space-y-2 text-[13px]">
            {config.map(([k, v]) => (
              <div key={k}>
                <dt className="text-xs text-ink-muted">{k.replace(/_/g, " ")}</dt>
                <dd className="font-mono text-[12px] break-all text-ink">{String(v)}</dd>
              </div>
            ))}
            <div>
              <dt className="text-xs text-ink-muted">credentials</dt>
              <dd className="text-ink-secondary">Encrypted · never displayed</dd>
            </div>
          </dl>
        ) : (
          <p className="text-[13px] text-ink-muted">Data arrives through the files you upload.</p>
        )}
        {c.connector !== "csv" && canManage ? (
          <>
            <Field label="Sync every">
              {(p) => (
                <Select
                  {...p}
                  value={String(c.sync_interval_minutes)}
                  onChange={(e) =>
                    update.mutate(Number(e.target.value), {
                      onSuccess: () => toast({ tone: "success", title: "Sync interval saved" }),
                      onError: (err) => toast({ tone: "danger", title: "Not saved", description: errorMessage(err) }),
                    })
                  }
                >
                  {[5, 15, 30, 60, 240, 1440].map((m) => (
                    <option key={m} value={m}>
                      {m < 60 ? `${m} minutes` : m === 60 ? "hour" : m === 1440 ? "day" : `${m / 60} hours`}
                    </option>
                  ))}
                </Select>
              )}
            </Field>
            <Button variant="secondary" size="sm" onClick={() => setRotating(true)}>
              Update credentials
            </Button>
            <RotateDialog connection={c} open={rotating} onOpenChange={setRotating} />
          </>
        ) : null}
        <p className="text-xs text-ink-muted">Connected {formatDateTime(c.created_at)}</p>
      </PanelBody>
    </Panel>
  );
}

function Webhook({ connection: c }: { connection: Connection }) {
  const toast = useToast();
  return (
    <Panel aria-labelledby="webhook-title">
      <PanelHeader id="webhook-title" title="Webhooks" description="Add this address to the Shopify app's webhook subscriptions for instant updates." />
      <PanelBody className="space-y-3">
        <div className="flex items-center gap-2">
          <code className="min-w-0 flex-1 truncate rounded-[6px] bg-sunken px-2 py-1.5 font-mono text-[11px] text-ink">{c.webhook_url}</code>
          <Button
            size="icon-sm"
            variant="secondary"
            aria-label="Copy webhook address"
            onClick={async () => {
              try {
                await navigator.clipboard.writeText(c.webhook_url ?? "");
                toast({ tone: "success", title: "Webhook address copied" });
              } catch {
                toast({ tone: "danger", title: "Couldn't copy. Select the address and copy it manually." });
              }
            }}
          >
            <Copy aria-hidden />
          </Button>
        </div>
        <p className="text-xs text-ink-muted">
          {c.has_webhook_secret
            ? "Deliveries are verified with the app's API secret key; unsigned or forged requests are rejected."
            : "Add the app's API secret key in credentials to accept webhooks. Until then, scheduled syncs keep data current."}
        </p>
      </PanelBody>
    </Panel>
  );
}

const ENTITY: Record<string, [string, string]> = {
  locations: ["location", "locations"],
  suppliers: ["supplier", "suppliers"],
  products: ["product", "products"],
  supplier_products: ["supplier term", "supplier terms"],
  supplier_terms: ["supplier term", "supplier terms"],
  stock: ["stock level", "stock levels"],
  sales: ["daily sales figure", "daily sales figures"],
  purchase_orders: ["purchase order", "purchase orders"],
};

function countOf(entity: string, n: number): string {
  const [one, many] = ENTITY[entity] ?? [entity.replace(/_/g, " "), entity.replace(/_/g, " ")];
  return `${n.toLocaleString("en-GB")} ${n === 1 ? one : many}`;
}

function statsSummary(job: SyncJob): string {
  const parts = Object.entries(job.stats).map(([entity, s]) => countOf(entity, s.written ?? 0));
  return parts.join(" · ") || "—";
}

const TRIGGER: Record<SyncJob["trigger"], string> = {
  initial: "First sync",
  schedule: "Scheduled",
  manual: "Requested",
  webhook: "Webhook",
  upload: "File upload",
};

function SyncHistory({ connection: c }: { connection: Connection }) {
  const jobs = useSyncJobs(c.id);
  return (
    <Panel aria-labelledby="history-title">
      <PanelHeader id="history-title" title={c.connector === "csv" ? "Import history" : "Sync history"} description="Records written per run." />
      {jobs.isPending ? (
        <div role="status" aria-label="Loading" className="border-t border-line p-5">
          <Skeleton className="h-9 w-full" />
        </div>
      ) : jobs.isError ? (
        <ErrorState compact onRetry={() => jobs.refetch()} />
      ) : jobs.data.length === 0 ? (
        <EmptyState compact title={c.connector === "csv" ? "No files imported yet" : "No syncs yet"} />
      ) : (
        <TableScroll className="border-t border-line">
          <Table>
            <thead>
              <tr>
                <Th>Started</Th>
                <Th>Trigger</Th>
                <Th>Result</Th>
                <Th>Written</Th>
              </tr>
            </thead>
            <tbody>
              {jobs.data.map((j) => (
                <Tr key={j.id}>
                  <Td className="font-mono text-[11px] whitespace-nowrap text-ink-muted">{formatDateTime(j.started_at)}</Td>
                  <Td className="text-ink-secondary">{TRIGGER[j.trigger]}</Td>
                  <Td>
                    {j.status === "succeeded" ? (
                      <Badge tone="success">Succeeded</Badge>
                    ) : j.status === "running" ? (
                      <Badge tone="info">Running</Badge>
                    ) : (
                      <span title={j.error ?? undefined}>
                        <Badge tone="danger">Failed</Badge>
                      </span>
                    )}
                  </Td>
                  <Td className="text-[12px] text-ink-secondary">
                    {j.status === "failed" ? <span className="text-danger">{j.error}</span> : statsSummary(j)}
                  </Td>
                </Tr>
              ))}
            </tbody>
          </Table>
        </TableScroll>
      )}
    </Panel>
  );
}

function Events({ connection: c }: { connection: Connection }) {
  const events = useEvents(c.id, true);
  return (
    <Panel aria-labelledby="events-title">
      <PanelHeader id="events-title" title="Recent webhook deliveries" description="Each delivery is recorded once and triggers an incremental sync." />
      {events.data?.length ? (
        <TableScroll className="border-t border-line">
          <Table>
            <thead>
              <tr>
                <Th>Received</Th>
                <Th>Topic</Th>
                <Th>Status</Th>
              </tr>
            </thead>
            <tbody>
              {events.data.map((e) => (
                <Tr key={e.id}>
                  <Td className="font-mono text-[11px] text-ink-muted">{formatDateTime(e.received_at)}</Td>
                  <Td className="font-mono text-[12px]">{e.topic}</Td>
                  <Td>
                    <Badge tone={e.status === "processed" ? "success" : e.status === "pending" ? "info" : "neutral"}>
                      {e.status === "processed" ? "Processed" : e.status === "pending" ? "Pending" : "Ignored"}
                    </Badge>
                  </Td>
                </Tr>
              ))}
            </tbody>
          </Table>
        </TableScroll>
      ) : (
        <EmptyState compact title="No deliveries yet" />
      )}
    </Panel>
  );
}

function CsvUpload({ connection: c }: { connection: Connection }) {
  const toast = useToast();
  const fileRef = useRef<HTMLInputElement>(null);
  const [kind, setKind] = useState<ImportKind>("locations");
  const [file, setFile] = useState<File | null>(null);
  const [result, setResult] = useState<UploadResult | null>(null);
  const upload = useIntegrationMutation(({ k, f }: { k: ImportKind; f: File }) => uploadCsv(c.id, k, f));
  const help = IMPORT_KINDS.find((k) => k.key === kind)?.help;

  return (
    <Panel aria-labelledby="upload-title">
      <PanelHeader
        id="upload-title"
        title="Import a file"
        description="Files are checked completely first. If any row has a problem, nothing is imported."
      />
      <PanelBody className="space-y-4">
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="What the file contains" hint={help}>
            {(p) => (
              <Select {...p} value={kind} onChange={(e) => { setKind(e.target.value as ImportKind); setResult(null); }}>
                {IMPORT_KINDS.map((k) => (
                  <option key={k.key} value={k.key}>
                    {k.label}
                  </option>
                ))}
              </Select>
            )}
          </Field>
          <Field label="CSV file" hint="UTF-8, up to 5 MB and 50,000 rows.">
            {(p) => (
              <Input
                {...p}
                ref={fileRef}
                type="file"
                accept=".csv,text/csv"
                className="h-10 py-1.5 file:mr-3 file:rounded-[6px] file:border-0 file:bg-sunken file:px-2 file:py-1 file:text-[13px] file:text-ink"
                onChange={(e) => { setFile(e.target.files?.[0] ?? null); setResult(null); }}
              />
            )}
          </Field>
        </div>
        <div className="flex flex-wrap items-center gap-3">
          <Button
            disabled={!file}
            loading={upload.isPending}
            onClick={() =>
              file &&
              upload.mutate(
                { k: kind, f: file },
                {
                  onSuccess: (r) => {
                    setResult(r);
                    if (r.accepted) {
                      toast({ tone: "success", title: `Imported ${r.rows} ${r.rows === 1 ? "row" : "rows"}`, description: `${countOf(kind, r.written)} saved.` });
                      setFile(null);
                      if (fileRef.current) fileRef.current.value = "";
                    }
                  },
                  onError: (e) => toast({ tone: "danger", title: "Not imported", description: errorMessage(e) }),
                },
              )
            }
          >
            <Upload aria-hidden /> Import
          </Button>
          <a
            href={`/api/v1/integrations/csv-templates/${kind}`}
            onClick={async (e) => {
              // Template requests need the organisation header, so fetch rather than navigate.
              e.preventDefault();
              const text = await api.get<string>(`/integrations/csv-templates/${kind}`, { text: true }).catch(() => null);
              if (typeof text !== "string") return;
              const url = URL.createObjectURL(new Blob([text], { type: "text/csv" }));
              const a = document.createElement("a");
              a.href = url;
              a.download = `operon-${kind}-template.csv`;
              a.click();
              URL.revokeObjectURL(url);
            }}
            className="inline-flex items-center gap-1.5 text-[13px] text-ink-secondary underline-offset-4 hover:text-ink hover:underline"
          >
            <Download className="size-4" aria-hidden /> Download template
          </a>
        </div>
        {result && !result.accepted ? (
          <div role="alert" className="space-y-2">
            <InlineAlert tone="danger" title={`Nothing was imported: ${result.error_count} problem${result.error_count === 1 ? "" : "s"} found`}>
              Fix the rows below and upload the file again.
              {result.error_count > result.errors.length ? ` Showing the first ${result.errors.length}.` : ""}
            </InlineAlert>
            <TableScroll className="rounded-[10px] border border-line">
              <Table>
                <thead>
                  <tr>
                    <Th numeric>Row</Th>
                    <Th>Column</Th>
                    <Th>Problem</Th>
                  </tr>
                </thead>
                <tbody>
                  {result.errors.map((e, i) => (
                    <Tr key={i}>
                      <Td numeric>{e.row}</Td>
                      <Td className="font-mono text-[12px]">{e.column ?? "—"}</Td>
                      <Td>{e.message}</Td>
                    </Tr>
                  ))}
                </tbody>
              </Table>
            </TableScroll>
          </div>
        ) : null}
      </PanelBody>
    </Panel>
  );
}
