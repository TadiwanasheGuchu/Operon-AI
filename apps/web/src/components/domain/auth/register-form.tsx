"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { MailCheck } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { useForm } from "react-hook-form";
import type { z } from "zod";

import { InlineAlert } from "@/components/feedback/inline-alert";
import { Button } from "@/components/ui/button";
import { Field, Input } from "@/components/ui/form";
import { MIN_PASSWORD, registerSchema } from "@/features/auth/schemas";
import { api, errorMessage } from "@/lib/api/client";

import { AuthHeading } from "./auth-heading";

type Values = z.infer<typeof registerSchema>;

export function RegisterForm() {
  const [sentTo, setSentTo] = useState<string | null>(null);
  const [error, setError] = useState<unknown>(null);
  const form = useForm<Values>({ resolver: zodResolver(registerSchema) });
  const errors = form.formState.errors;

  async function onSubmit(values: Values) {
    setError(null);
    try {
      await api.post("/auth/register", values, { tenant: false });
      setSentTo(values.email);
    } catch (e) {
      setError(e);
    }
  }

  if (sentTo) return <CheckInbox email={sentTo} />;

  return (
    <>
      <AuthHeading
        title="Create your organisation"
        description="You'll be its owner and can invite your team once you're in."
      />
      <form onSubmit={form.handleSubmit(onSubmit)} noValidate className="space-y-5">
        {error ? <InlineAlert tone="danger" title={errorMessage(error)} /> : null}
        <Field label="Your name" error={errors.full_name?.message}>
          {(p) => <Input {...p} {...form.register("full_name")} autoComplete="name" autoFocus />}
        </Field>
        <Field label="Work email" error={errors.email?.message}>
          {(p) => <Input {...p} {...form.register("email")} type="email" autoComplete="email" />}
        </Field>
        <Field
          label="Password"
          hint={`At least ${MIN_PASSWORD} characters. A memorable phrase is stronger than a short complex word.`}
          error={errors.password?.message}
        >
          {(p) => <Input {...p} {...form.register("password")} type="password" autoComplete="new-password" />}
        </Field>
        <Field label="Organisation name" hint="You can change this later." error={errors.organisation_name?.message}>
          {(p) => <Input {...p} {...form.register("organisation_name")} autoComplete="organization" />}
        </Field>
        <Button type="submit" className="w-full" loading={form.formState.isSubmitting}>
          Create organisation
        </Button>
      </form>
      <p className="mt-8 text-center text-sm text-ink-secondary">
        Already have an account?{" "}
        <Link href="/login" className="font-medium text-ink underline-offset-4 hover:underline">
          Sign in
        </Link>
      </p>
    </>
  );
}

export function CheckInbox({ email, purpose = "confirm" }: { email: string; purpose?: "confirm" | "reset" }) {
  return (
    <div role="status">
      <span className="inline-flex size-11 items-center justify-center rounded-full bg-success-bg text-success">
        <MailCheck className="size-5" aria-hidden />
      </span>
      <AuthHeading
        title="Check your inbox"
        description={
          <>
            If <strong className="font-medium text-ink">{email}</strong> can receive{" "}
            {purpose === "confirm" ? "a confirmation link" : "a reset link"}, it&apos;s on its way. The link
            expires {purpose === "confirm" ? "in 24 hours" : "in 30 minutes"}.
          </>
        }
      />
      <Link href="/login" className="text-sm font-medium text-ink underline-offset-4 hover:underline">
        Back to sign in
      </Link>
    </div>
  );
}
