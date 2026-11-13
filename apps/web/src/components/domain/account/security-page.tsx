"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Copy, Download, Monitor, ShieldCheck } from "lucide-react";
import QRCode from "qrcode";
import { useEffect, useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";

import { ConfirmDialog } from "@/components/feedback/confirm-dialog";
import { InlineAlert } from "@/components/feedback/inline-alert";
import { ErrorState } from "@/components/feedback/states";
import { useToast } from "@/components/feedback/toast";
import { PageContainer, PageHeader } from "@/components/layout/page-header";
import { Badge, StatusBadge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogTitle } from "@/components/ui/dialog";
import { Field, Input } from "@/components/ui/form";
import { Panel, PanelBody, PanelHeader } from "@/components/ui/panel";
import { Skeleton } from "@/components/ui/skeleton";
import { changePasswordSchema, MIN_PASSWORD } from "@/features/auth/schemas";
import { sessionKey } from "@/features/session/use-session";
import { useWorkspace } from "@/features/workspace/workspace-context";
import { api, errorMessage } from "@/lib/api/client";
import { formatDateTime, formatRelative } from "@/lib/format";

export function SecurityPage() {
  return (
    <PageContainer narrow>
      <PageHeader title="Security" description="Protect your account and see where you're signed in." />
      <TwoFactorPanel />
      <PasswordPanel />
      <SessionsPanel />
    </PageContainer>
  );
}

// --- Two-factor --------------------------------------------------------------------------------

const codeSchema = z.object({ code: z.string().trim().regex(/^\d{6}$/, "Enter the 6-digit code from your app.") });

function TwoFactorPanel() {
  const { workspace } = useWorkspace();
  const enabled = workspace.user?.mfaEnabled ?? false;
  const queryClient = useQueryClient();
  const toast = useToast();
  const [setup, setSetup] = useState<{ secret: string; otpauth_uri: string } | null>(null);
  const [codes, setCodes] = useState<string[] | null>(null);
  const [disabling, setDisabling] = useState(false);
  const [regenerating, setRegenerating] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const start = useMutation({ mutationFn: () => api.post<{ secret: string; otpauth_uri: string }>("/auth/mfa/totp/setup", undefined, { tenant: false }) });

  const refresh = () =>
    Promise.all([
      queryClient.invalidateQueries({ queryKey: sessionKey }),
      queryClient.invalidateQueries({ predicate: (q) => q.queryKey[0] === "tenant" }),
    ]);

  return (
    <Panel className="mt-6" aria-labelledby="mfa-title">
      <PanelHeader
        id="mfa-title"
        title="Two-factor authentication"
        description="A code from an authenticator app is needed at sign-in, as well as your password."
        actions={enabled ? <StatusBadge status="healthy" label="On" /> : <StatusBadge status="attention" label="Off" />}
      />
      <PanelBody className="space-y-4">
        {error ? <InlineAlert tone="danger" title={errorMessage(error)} /> : null}
        {enabled ? (
          <div className="flex flex-wrap gap-2">
            <Button variant="secondary" onClick={() => setRegenerating(true)}>
              New recovery codes
            </Button>
            <Button variant="tertiary" className="text-danger hover:text-danger" onClick={() => setDisabling(true)}>
              Turn off
            </Button>
          </div>
        ) : setup ? (
          <SetupSteps
            setup={setup}
            onCancel={() => setSetup(null)}
            onConfirmed={async (recovery) => {
              setSetup(null);
              setCodes(recovery);
              await refresh();
              toast({ tone: "success", title: "Two-factor authentication is on" });
            }}
          />
        ) : (
          <Button
            loading={start.isPending}
            onClick={() => {
              setError(null);
              start.mutate(undefined, { onSuccess: setSetup, onError: setError });
            }}
          >
            <ShieldCheck aria-hidden /> Set up two-factor authentication
          </Button>
        )}
      </PanelBody>

      <RecoveryCodesDialog codes={codes} onClose={() => setCodes(null)} />
      <CodeDialog
        open={regenerating}
        onOpenChange={setRegenerating}
        title="Generate new recovery codes"
        description="Your current recovery codes will stop working. Enter a code from your authenticator app to continue."
        submitLabel="Generate codes"
        onSubmit={async ({ code }) => {
          const r = await api.post<{ recovery_codes: string[] }>("/auth/mfa/recovery-codes", { code }, { tenant: false });
          setCodes(r.recovery_codes);
        }}
      />
      <DisableDialog
        open={disabling}
        onOpenChange={setDisabling}
        onDone={async () => {
          await refresh();
          toast({ tone: "info", title: "Two-factor authentication is off" });
        }}
      />
    </Panel>
  );
}

function SetupSteps({
  setup,
  onCancel,
  onConfirmed,
}: {
  setup: { secret: string; otpauth_uri: string };
  onCancel: () => void;
  onConfirmed: (codes: string[]) => Promise<void>;
}) {
  const [qr, setQr] = useState<string | null>(null);
  const [error, setError] = useState<unknown>(null);
  const form = useForm<z.infer<typeof codeSchema>>({ resolver: zodResolver(codeSchema) });

  useEffect(() => {
    // Rendered locally: the secret never leaves the browser for a third-party QR service.
    QRCode.toString(setup.otpauth_uri, { type: "svg", margin: 0, color: { dark: "#0D2638", light: "#FFFFFF" } })
      .then(setQr)
      .catch(() => setQr(null));
  }, [setup.otpauth_uri]);

  const grouped = setup.secret.match(/.{1,4}/g)?.join(" ") ?? setup.secret;
  return (
    <ol className="space-y-5">
      <li>
        <p className="text-sm font-medium text-ink">1. Scan this code with your authenticator app</p>
        <p className="mt-0.5 text-[13px] text-ink-muted">For example 1Password, Google Authenticator or Microsoft Authenticator.</p>
        <div className="mt-3 flex flex-wrap items-center gap-5">
          <div
            className="size-40 rounded-[10px] border border-line bg-raised p-3 [&_svg]:size-full"
            role="img"
            aria-label="QR code for your authenticator app"
            dangerouslySetInnerHTML={qr ? { __html: qr } : undefined}
          />
          <div className="min-w-0">
            <p className="text-xs text-ink-muted">Can&apos;t scan? Enter this key instead:</p>
            <p className="mt-1 font-mono text-sm tracking-wide break-all text-ink">{grouped}</p>
          </div>
        </div>
      </li>
      <li>
        <p className="text-sm font-medium text-ink">2. Enter the 6-digit code it shows</p>
        <form
          noValidate
          className="mt-3 flex flex-wrap items-start gap-2"
          onSubmit={form.handleSubmit(async ({ code }) => {
            setError(null);
            try {
              const r = await api.post<{ recovery_codes: string[] }>("/auth/mfa/totp/confirm", { code }, { tenant: false });
              await onConfirmed(r.recovery_codes);
            } catch (e) {
              setError(e);
            }
          })}
        >
          <Field label="Authentication code" error={form.formState.errors.code?.message ?? (error ? errorMessage(error) : undefined)} className="w-48">
            {(p) => <Input {...p} {...form.register("code")} inputMode="numeric" autoComplete="one-time-code" className="font-mono tracking-[0.2em]" />}
          </Field>
          <div className="flex gap-2 pt-6">
            <Button type="submit" loading={form.formState.isSubmitting}>
              Turn on
            </Button>
            <Button type="button" variant="tertiary" onClick={onCancel}>
              Cancel
            </Button>
          </div>
        </form>
      </li>
    </ol>
  );
}

function RecoveryCodesDialog({ codes, onClose }: { codes: string[] | null; onClose: () => void }) {
  const toast = useToast();
  const [saved, setSaved] = useState(false);
  const text = codes?.join("\n") ?? "";
  return (
    <Dialog
      open={Boolean(codes)}
      onOpenChange={(o) => {
        if (!o && saved) {
          onClose();
          setSaved(false);
        }
      }}
    >
      <DialogContent className="p-6" hideClose onEscapeKeyDown={(e) => !saved && e.preventDefault()} onPointerDownOutside={(e) => e.preventDefault()}>
        <DialogTitle className="text-base font-semibold text-ink">Save your recovery codes</DialogTitle>
        <DialogDescription className="mt-1 text-[13px] text-ink-secondary">
          If you lose your phone, each code signs you in once. This is the only time they&apos;re shown.
        </DialogDescription>
        <ul className="mt-4 grid grid-cols-2 gap-x-6 gap-y-1.5 rounded-[10px] border border-line bg-canvas p-4 font-mono text-sm text-ink">
          {codes?.map((c) => (
            <li key={c}>{c}</li>
          ))}
        </ul>
        <div className="mt-3 flex flex-wrap gap-2">
          <Button
            size="sm"
            variant="secondary"
            onClick={async () => {
              try {
                await navigator.clipboard.writeText(text);
                toast({ tone: "success", title: "Recovery codes copied" });
              } catch {
                toast({ tone: "danger", title: "Couldn't copy. Select the codes and copy them manually." });
              }
            }}
          >
            <Copy aria-hidden /> Copy
          </Button>
          <Button size="sm" variant="secondary" asChild>
            <a href={`data:text/plain;charset=utf-8,${encodeURIComponent(`Operon recovery codes\n\n${text}\n`)}`} download="operon-recovery-codes.txt">
              <Download aria-hidden /> Download
            </a>
          </Button>
        </div>
        <label className="mt-5 flex items-center gap-2 text-sm text-ink">
          <input type="checkbox" checked={saved} onChange={(e) => setSaved(e.target.checked)} className="size-4 accent-[var(--color-ocean)]" />
          I&apos;ve saved these codes somewhere safe
        </label>
        <div className="mt-5 flex justify-end">
          <Button disabled={!saved} onClick={() => { onClose(); setSaved(false); }}>
            Done
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}

function CodeDialog({
  open,
  onOpenChange,
  title,
  description,
  submitLabel,
  onSubmit,
}: {
  open: boolean;
  onOpenChange: (o: boolean) => void;
  title: string;
  description: string;
  submitLabel: string;
  onSubmit: (v: z.infer<typeof codeSchema>) => Promise<void>;
}) {
  const [error, setError] = useState<unknown>(null);
  const form = useForm<z.infer<typeof codeSchema>>({ resolver: zodResolver(codeSchema) });
  return (
    <Dialog open={open} onOpenChange={(o) => { onOpenChange(o); if (!o) { form.reset(); setError(null); } }}>
      <DialogContent className="p-6">
        <DialogTitle className="text-base font-semibold text-ink">{title}</DialogTitle>
        <DialogDescription className="mt-1 mb-5 text-[13px] text-ink-secondary">{description}</DialogDescription>
        <form
          noValidate
          className="space-y-5"
          onSubmit={form.handleSubmit(async (v) => {
            setError(null);
            try {
              await onSubmit(v);
              onOpenChange(false);
              form.reset();
            } catch (e) {
              setError(e);
            }
          })}
        >
          {error ? <InlineAlert tone="danger" title={errorMessage(error)} /> : null}
          <Field label="Authentication code" error={form.formState.errors.code?.message}>
            {(p) => <Input {...p} {...form.register("code")} inputMode="numeric" autoComplete="one-time-code" autoFocus className="font-mono tracking-[0.2em]" />}
          </Field>
          <div className="flex justify-end gap-2">
            <Button type="button" variant="secondary" onClick={() => onOpenChange(false)}>
              Cancel
            </Button>
            <Button type="submit" loading={form.formState.isSubmitting}>
              {submitLabel}
            </Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  );
}

const disableSchema = z.object({
  password: z.string().min(1, "Enter your password."),
  code: z.string().trim().min(6, "Enter a code from your app, or a recovery code."),
});

function DisableDialog({ open, onOpenChange, onDone }: { open: boolean; onOpenChange: (o: boolean) => void; onDone: () => Promise<void> }) {
  const [error, setError] = useState<unknown>(null);
  const form = useForm<z.infer<typeof disableSchema>>({ resolver: zodResolver(disableSchema) });
  return (
    <Dialog open={open} onOpenChange={(o) => { onOpenChange(o); if (!o) { form.reset(); setError(null); } }}>
      <DialogContent className="p-6">
        <DialogTitle className="text-base font-semibold text-ink">Turn off two-factor authentication?</DialogTitle>
        <DialogDescription className="mt-1 mb-5 text-[13px] text-ink-secondary">
          Your account will be protected by your password alone. Organisations that require two-factor will block you until you turn it back on.
        </DialogDescription>
        <form
          noValidate
          className="space-y-4"
          onSubmit={form.handleSubmit(async (v) => {
            setError(null);
            try {
              await api.post("/auth/mfa/totp/disable", v, { tenant: false });
              onOpenChange(false);
              form.reset();
              await onDone();
            } catch (e) {
              setError(e);
            }
          })}
        >
          {error ? <InlineAlert tone="danger" title={errorMessage(error)} /> : null}
          <Field label="Password" error={form.formState.errors.password?.message}>
            {(p) => <Input {...p} {...form.register("password")} type="password" autoComplete="current-password" />}
          </Field>
          <Field label="Authentication or recovery code" error={form.formState.errors.code?.message}>
            {(p) => <Input {...p} {...form.register("code")} autoComplete="one-time-code" className="font-mono" />}
          </Field>
          <div className="flex justify-end gap-2 pt-1">
            <Button type="button" variant="secondary" onClick={() => onOpenChange(false)}>
              Keep it on
            </Button>
            <Button type="submit" variant="destructive" loading={form.formState.isSubmitting}>
              Turn off
            </Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  );
}

// --- Password ----------------------------------------------------------------------------------

function PasswordPanel() {
  const toast = useToast();
  const queryClient = useQueryClient();
  const [error, setError] = useState<unknown>(null);
  const form = useForm<z.infer<typeof changePasswordSchema>>({ resolver: zodResolver(changePasswordSchema) });
  return (
    <Panel className="mt-5" aria-labelledby="password-title">
      <PanelHeader id="password-title" title="Password" description="Changing it signs you out on your other devices." />
      <PanelBody>
        <form
          noValidate
          className="space-y-4"
          onSubmit={form.handleSubmit(async (v) => {
            setError(null);
            try {
              await api.post("/auth/password/change", { current_password: v.current_password, new_password: v.new_password }, { tenant: false });
              form.reset();
              await queryClient.invalidateQueries({ queryKey: ["account", "sessions"] });
              toast({ tone: "success", title: "Password changed", description: "Your other sessions were signed out." });
            } catch (e) {
              setError(e);
            }
          })}
        >
          {error ? <InlineAlert tone="danger" title={errorMessage(error)} /> : null}
          <Field label="Current password" error={form.formState.errors.current_password?.message}>
            {(p) => <Input {...p} {...form.register("current_password")} type="password" autoComplete="current-password" />}
          </Field>
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label="New password" hint={`At least ${MIN_PASSWORD} characters.`} error={form.formState.errors.new_password?.message}>
              {(p) => <Input {...p} {...form.register("new_password")} type="password" autoComplete="new-password" />}
            </Field>
            <Field label="Confirm new password" error={form.formState.errors.confirm?.message}>
              {(p) => <Input {...p} {...form.register("confirm")} type="password" autoComplete="new-password" />}
            </Field>
          </div>
          <Button type="submit" loading={form.formState.isSubmitting}>
            Change password
          </Button>
        </form>
      </PanelBody>
    </Panel>
  );
}

// --- Sessions ----------------------------------------------------------------------------------

interface AccountSession {
  id: string;
  created_at: string;
  last_seen_at: string;
  expires_at: string;
  ip_address: string | null;
  user_agent: string | null;
  current: boolean;
}

function describeAgent(ua: string | null): string {
  if (!ua) return "Unknown device";
  const browser = /Edg\//.test(ua) ? "Edge" : /Chrome\//.test(ua) ? "Chrome" : /Firefox\//.test(ua) ? "Firefox" : /Safari\//.test(ua) ? "Safari" : "Browser";
  const os = /Windows/.test(ua) ? "Windows" : /Mac OS X/.test(ua) ? "macOS" : /Android/.test(ua) ? "Android" : /iPhone|iPad/.test(ua) ? "iOS" : /Linux/.test(ua) ? "Linux" : "";
  return os ? `${browser} on ${os}` : browser;
}

function SessionsPanel() {
  const toast = useToast();
  const queryClient = useQueryClient();
  const [revoking, setRevoking] = useState<AccountSession | null>(null);
  const sessions = useQuery({ queryKey: ["account", "sessions"], queryFn: () => api.get<AccountSession[]>("/auth/sessions", { tenant: false }) });
  return (
    <Panel className="mt-5" aria-labelledby="sessions-title">
      <PanelHeader id="sessions-title" title="Where you're signed in" description="Sessions end after 60 minutes of inactivity, and always after 12 hours." />
      {sessions.isPending ? (
        <div role="status" aria-label="Loading sessions" className="space-y-3 border-t border-line p-5">
          <Skeleton className="h-10 w-full" />
        </div>
      ) : sessions.isError ? (
        <ErrorState compact onRetry={() => sessions.refetch()} />
      ) : (
        <ul className="divide-y divide-line border-t border-line">
          {sessions.data.map((s) => (
            <li key={s.id} className="flex items-center gap-3 px-5 py-3">
              <Monitor className="size-5 shrink-0 text-icon" aria-hidden />
              <div className="min-w-0 flex-1">
                <p className="text-[13px] font-medium text-ink">
                  {describeAgent(s.user_agent)} {s.current ? <Badge tone="success" className="ml-1">This device</Badge> : null}
                </p>
                <p className="font-mono text-[11px] text-ink-muted">
                  {s.ip_address ?? "Unknown IP"} · signed in {formatDateTime(s.created_at)} · active {formatRelative(s.last_seen_at)}
                </p>
              </div>
              {s.current ? null : (
                <Button size="sm" variant="tertiary" onClick={() => setRevoking(s)}>
                  Sign out
                </Button>
              )}
            </li>
          ))}
        </ul>
      )}
      <ConfirmDialog
        open={Boolean(revoking)}
        onOpenChange={(o) => !o && setRevoking(null)}
        title="Sign out this session?"
        description={revoking ? `${describeAgent(revoking.user_agent)} will be signed out immediately.` : ""}
        confirmLabel="Sign out session"
        onConfirm={async () => {
          if (!revoking) return;
          try {
            await api.delete(`/auth/sessions/${revoking.id}`, { tenant: false });
            await queryClient.invalidateQueries({ queryKey: ["account", "sessions"] });
            toast({ tone: "success", title: "Session signed out" });
          } catch (e) {
            toast({ tone: "danger", title: "Couldn't sign out that session", description: errorMessage(e) });
          }
        }}
      />
    </Panel>
  );
}
