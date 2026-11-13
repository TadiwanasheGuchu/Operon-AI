"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { CircleCheck, CircleX, LoaderCircle } from "lucide-react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { useForm } from "react-hook-form";
import type { z } from "zod";

import { InlineAlert } from "@/components/feedback/inline-alert";
import { Button } from "@/components/ui/button";
import { Field, Input } from "@/components/ui/form";
import { emailSchema, MIN_PASSWORD, resetSchema } from "@/features/auth/schemas";
import { api, errorMessage } from "@/lib/api/client";

import { AuthHeading } from "./auth-heading";
import { CheckInbox } from "./register-form";

export function VerifyEmail() {
  const token = useSearchParams().get("token");
  const router = useRouter();
  const [state, setState] = useState<{ status: "working" | "done" | "failed"; message?: string }>({
    status: token ? "working" : "failed",
    message: token ? undefined : "This link is incomplete. Open the link from your email again.",
  });
  const sent = useRef(false);

  useEffect(() => {
    if (!token || sent.current) return;
    sent.current = true; // single-use token: never post twice (e.g. React strict mode)
    api
      .post("/auth/verify-email", { token }, { tenant: false })
      .then(() => {
        setState({ status: "done" });
        setTimeout(() => router.replace("/login?verified=1"), 1200);
      })
      .catch((e: unknown) => setState({ status: "failed", message: errorMessage(e) }));
  }, [token, router]);

  return (
    <div role="status" aria-live="polite">
      {state.status === "working" ? (
        <>
          <LoaderCircle className="size-6 animate-spin text-icon" aria-hidden />
          <AuthHeading title="Confirming your email…" />
        </>
      ) : state.status === "done" ? (
        <>
          <CircleCheck className="size-7 text-success" aria-hidden />
          <AuthHeading title="Email confirmed" description="Taking you to sign in…" />
        </>
      ) : (
        <>
          <CircleX className="size-7 text-danger" aria-hidden />
          <AuthHeading title="We couldn't confirm your email" description={state.message} />
          <p className="text-sm text-ink-secondary">
            Sign in to request a new confirmation link.{" "}
            <Link href="/login" className="font-medium text-ink underline-offset-4 hover:underline">
              Go to sign in
            </Link>
          </p>
        </>
      )}
    </div>
  );
}

export function ForgotPassword() {
  const [sentTo, setSentTo] = useState<string | null>(null);
  const [error, setError] = useState<unknown>(null);
  const form = useForm<z.infer<typeof emailSchema>>({ resolver: zodResolver(emailSchema) });
  if (sentTo) return <CheckInbox email={sentTo} purpose="reset" />;
  return (
    <>
      <AuthHeading title="Reset your password" description="We'll email you a link to choose a new one." />
      <form
        noValidate
        className="space-y-5"
        onSubmit={form.handleSubmit(async (v) => {
          setError(null);
          try {
            await api.post("/auth/password/forgot", v, { tenant: false });
            setSentTo(v.email);
          } catch (e) {
            setError(e);
          }
        })}
      >
        {error ? <InlineAlert tone="danger" title={errorMessage(error)} /> : null}
        <Field label="Email" error={form.formState.errors.email?.message}>
          {(p) => <Input {...p} {...form.register("email")} type="email" autoComplete="email" autoFocus />}
        </Field>
        <Button type="submit" className="w-full" loading={form.formState.isSubmitting}>
          Send reset link
        </Button>
        <Link href="/login" className="block text-center text-sm text-ink-secondary hover:text-ink">
          Back to sign in
        </Link>
      </form>
    </>
  );
}

export function ResetPassword() {
  const token = useSearchParams().get("token");
  const router = useRouter();
  const [error, setError] = useState<unknown>(null);
  const form = useForm<z.infer<typeof resetSchema>>({ resolver: zodResolver(resetSchema) });
  if (!token) {
    return (
      <AuthHeading
        title="This link is incomplete"
        description={
          <>
            Open the link from your email again, or{" "}
            <Link href="/forgot-password" className="font-medium text-ink underline">
              request a new one
            </Link>
            .
          </>
        }
      />
    );
  }
  return (
    <>
      <AuthHeading
        title="Choose a new password"
        description="You'll be signed out on every device, then you can sign in with the new password."
      />
      <form
        noValidate
        className="space-y-5"
        onSubmit={form.handleSubmit(async (v) => {
          setError(null);
          try {
            await api.post("/auth/password/reset", { token, password: v.password }, { tenant: false });
            router.replace("/login?reset=1");
          } catch (e) {
            setError(e);
          }
        })}
      >
        {error ? (
          <InlineAlert tone="danger" title={errorMessage(error)}>
            <Link href="/forgot-password" className="underline">
              Request a new link
            </Link>
          </InlineAlert>
        ) : null}
        <Field label="New password" hint={`At least ${MIN_PASSWORD} characters.`} error={form.formState.errors.password?.message}>
          {(p) => <Input {...p} {...form.register("password")} type="password" autoComplete="new-password" autoFocus />}
        </Field>
        <Field label="Confirm new password" error={form.formState.errors.confirm?.message}>
          {(p) => <Input {...p} {...form.register("confirm")} type="password" autoComplete="new-password" />}
        </Field>
        <Button type="submit" className="w-full" loading={form.formState.isSubmitting}>
          Change password
        </Button>
      </form>
    </>
  );
}
