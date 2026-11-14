"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useState } from "react";
import { useForm } from "react-hook-form";
import type { z } from "zod";

import { InlineAlert } from "@/components/feedback/inline-alert";
import { Button } from "@/components/ui/button";
import { Field, Input } from "@/components/ui/form";
import { loginSchema, mfaSchema, safeNext } from "@/features/auth/schemas";
import { sessionKey } from "@/features/session/use-session";
import { api, ApiRequestError, errorMessage } from "@/lib/api/client";

import { AuthHeading } from "./auth-heading";

type LoginValues = z.infer<typeof loginSchema>;

/** Messages for the `sso_error` the API's callback redirects back with. */
const SSO_ERRORS: Record<string, string> = {
  denied: "Your identity provider didn't approve the sign-in.",
  invalid: "The sign-in response was incomplete. Start again.",
  sso_state_invalid: "That sign-in link expired. Start again.",
  sso_failed: "Single sign-on didn't complete. Try again.",
  not_a_member: "You aren't a member of this organisation yet. Ask an administrator to invite you.",
  account_disabled: "This account is disabled.",
};

export function LoginForm() {
  const params = useSearchParams();
  const router = useRouter();
  const queryClient = useQueryClient();
  const [step, setStep] = useState<"password" | "mfa">("password");
  const [error, setError] = useState<ApiRequestError | Error | null>(null);
  const [email, setEmail] = useState("");
  const [resent, setResent] = useState(false);
  const [ssoBusy, setSsoBusy] = useState(false);

  async function startSso(address: string) {
    setError(null);
    if (!/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(address)) {
      setError(new Error("Enter your work email first, then choose single sign-on."));
      return;
    }
    setSsoBusy(true);
    try {
      const r = await api.post<{ redirect_url: string }>("/auth/sso/start", { email: address }, { tenant: false });
      window.location.assign(r.redirect_url);
    } catch (e) {
      setError(e as Error);
      setSsoBusy(false);
    }
  }

  async function finish() {
    await queryClient.invalidateQueries({ queryKey: sessionKey });
    router.replace(safeNext(params.get("next")));
  }

  const form = useForm<LoginValues>({ resolver: zodResolver(loginSchema) });
  async function onPassword(values: LoginValues) {
    setError(null);
    setResent(false);
    try {
      const r = await api.post<{ status: string }>("/auth/login", values, { tenant: false });
      setEmail(values.email);
      if (r.status === "mfa_required") setStep("mfa");
      else await finish();
    } catch (e) {
      setEmail(values.email);
      setError(e as Error);
    }
  }

  const mfa = useForm<z.infer<typeof mfaSchema>>({ resolver: zodResolver(mfaSchema) });
  async function onCode(values: z.infer<typeof mfaSchema>) {
    setError(null);
    try {
      await api.post("/auth/login/mfa", values, { tenant: false });
      await finish();
    } catch (e) {
      const err = e as ApiRequestError;
      if (err.code === "mfa_challenge_expired") setStep("password");
      setError(err);
      mfa.reset();
    }
  }

  const code = error instanceof ApiRequestError ? error.code : null;
  const reset = params.get("reset") === "1";
  const verified = params.get("verified") === "1";
  const ssoError = params.get("sso_error");

  if (step === "mfa") {
    return (
      <>
        <AuthHeading
          title="Two-factor authentication"
          description="Enter the 6-digit code from your authenticator app, or one of your recovery codes."
        />
        <form onSubmit={mfa.handleSubmit(onCode)} noValidate className="space-y-5">
          {error ? <InlineAlert tone="danger" title={errorMessage(error)} /> : null}
          <Field label="Authentication code" error={mfa.formState.errors.code?.message}>
            {(p) => (
              <Input
                {...p}
                {...mfa.register("code")}
                inputMode="numeric"
                autoComplete="one-time-code"
                autoFocus
                className="font-mono tracking-[0.2em]"
              />
            )}
          </Field>
          <Button type="submit" className="w-full" loading={mfa.formState.isSubmitting}>
            Verify and sign in
          </Button>
          <Button type="button" variant="tertiary" className="w-full" onClick={() => setStep("password")}>
            Use a different account
          </Button>
        </form>
      </>
    );
  }

  return (
    <>
      <AuthHeading title="Sign in" description="Welcome back to Operon." />
      <form onSubmit={form.handleSubmit(onPassword)} noValidate className="space-y-5">
        {reset ? <InlineAlert tone="success" title="Password changed. Sign in with your new password." /> : null}
        {verified ? <InlineAlert tone="success" title="Email confirmed. You can sign in now." /> : null}
        {ssoError && !error ? (
          <InlineAlert tone="danger" title={SSO_ERRORS[ssoError] ?? "Single sign-on didn't complete. Try again."} />
        ) : null}
        {code === "email_not_verified" ? (
          <InlineAlert
            tone="warning"
            title="Confirm your email address first"
            action={
              resent ? undefined : (
                <Button
                  size="sm"
                  variant="secondary"
                  onClick={async () => {
                    await api.post("/auth/verify-email/resend", { email }, { tenant: false }).catch(() => null);
                    setResent(true);
                  }}
                >
                  Resend link
                </Button>
              )
            }
          >
            {resent ? "If the address needs confirming, a new link is on its way." : "Check your inbox for the confirmation link."}
          </InlineAlert>
        ) : error ? (
          <InlineAlert tone="danger" title={errorMessage(error)}>
            {code === "rate_limited" ? "For your security, sign-in is paused for a few minutes." : null}
          </InlineAlert>
        ) : null}
        <Field label="Email" error={form.formState.errors.email?.message}>
          {(p) => <Input {...p} {...form.register("email")} type="email" autoComplete="username" autoFocus />}
        </Field>
        <Field label="Password" error={form.formState.errors.password?.message}>
          {(p) => <Input {...p} {...form.register("password")} type="password" autoComplete="current-password" />}
        </Field>
        <div className="flex justify-end">
          <Link href="/forgot-password" className="text-[13px] text-ink-secondary underline-offset-4 hover:text-ink hover:underline">
            Forgot your password?
          </Link>
        </div>
        <Button type="submit" className="w-full" loading={form.formState.isSubmitting}>
          Sign in
        </Button>
        <Button
          type="button"
          variant={code === "sso_required" ? "primary" : "secondary"}
          className="w-full"
          loading={ssoBusy}
          onClick={() => startSso(form.getValues("email")?.trim() ?? "")}
        >
          Sign in with SSO
        </Button>
        <p className="text-center text-xs text-ink-muted">Single sign-on uses the email above; no password needed.</p>
      </form>
      <p className="mt-8 text-center text-sm text-ink-secondary">
        New to Operon?{" "}
        <Link href="/register" className="font-medium text-ink underline-offset-4 hover:underline">
          Create an organisation
        </Link>
      </p>
    </>
  );
}
