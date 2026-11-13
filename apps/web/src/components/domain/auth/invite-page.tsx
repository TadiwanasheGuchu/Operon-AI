"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Building2, CircleX } from "lucide-react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useState } from "react";
import { useForm } from "react-hook-form";
import type { z } from "zod";

import { InlineAlert } from "@/components/feedback/inline-alert";
import { Button } from "@/components/ui/button";
import { Field, Input } from "@/components/ui/form";
import { Skeleton } from "@/components/ui/skeleton";
import { inviteRegisterSchema, MIN_PASSWORD } from "@/features/auth/schemas";
import { setActiveOrganisationId } from "@/features/session/active-organisation";
import { sessionKey, useSession } from "@/features/session/use-session";
import { api, errorMessage } from "@/lib/api/client";
import { formatDate } from "@/lib/format";

import { AuthHeading } from "./auth-heading";

interface Lookup {
  organisation_name: string;
  email: string;
  role_name: string;
  invited_by: string | null;
  expires_at: string;
  status: "open" | "expired" | "accepted" | "revoked";
}

const CLOSED: Record<Exclude<Lookup["status"], "open">, string> = {
  expired: "This invitation has expired. Ask the person who invited you to send a new one.",
  accepted: "This invitation has already been used. Sign in to reach the organisation.",
  revoked: "This invitation was withdrawn. Ask the person who invited you if you still need access.",
};

export function InvitePage() {
  const token = useSearchParams().get("token") ?? "";
  const session = useSession();
  const lookup = useQuery({
    queryKey: ["invitation", token],
    queryFn: () => api.get<Lookup>(`/invitations/lookup?token=${encodeURIComponent(token)}`, { tenant: false }),
    enabled: token.length >= 20,
    retry: false,
  });

  if (token.length < 20 || lookup.isError) {
    return (
      <>
        <CircleX className="size-7 text-danger" aria-hidden />
        <AuthHeading title="This invitation link isn't valid" description="Open the link from your email again, or ask for a new invitation." />
      </>
    );
  }
  if (lookup.isPending || session.isPending) {
    return (
      <div role="status" aria-label="Loading invitation" className="space-y-3">
        <Skeleton className="h-9 w-3/4" />
        <Skeleton className="h-4 w-full" />
        <Skeleton className="h-10 w-full" />
      </div>
    );
  }

  const invite = lookup.data;
  const heading = (
    <>
      <span className="inline-flex size-11 items-center justify-center rounded-[10px] bg-mist text-ocean">
        <Building2 className="size-5" aria-hidden />
      </span>
      <AuthHeading
        title={`Join ${invite.organisation_name}`}
        description={
          <>
            {invite.invited_by ? `${invite.invited_by} invited you` : "You've been invited"} to join as{" "}
            <strong className="font-medium text-ink">{invite.role_name}</strong>.
            {invite.status === "open" ? ` The invitation expires on ${formatDate(invite.expires_at)}.` : null}
          </>
        }
      />
    </>
  );

  if (invite.status !== "open") {
    return (
      <>
        {heading}
        <InlineAlert tone="warning" title={CLOSED[invite.status]} />
        <Link href="/login" className="mt-6 block text-sm font-medium text-ink underline-offset-4 hover:underline">
          Go to sign in
        </Link>
      </>
    );
  }

  const user = session.data?.user;
  if (user && user.email.toLowerCase() === invite.email.toLowerCase()) {
    return (
      <>
        {heading}
        <AcceptButton token={token} />
      </>
    );
  }
  if (user) {
    return (
      <>
        {heading}
        <InlineAlert tone="warning" title={`This invitation is for ${invite.email}`}>
          You&apos;re signed in as {user.email}. Sign out, then open the link again.
        </InlineAlert>
        <SignOutButton />
      </>
    );
  }
  return (
    <>
      {heading}
      <RegisterFromInvite token={token} email={invite.email} />
    </>
  );
}

function AcceptButton({ token }: { token: string }) {
  const router = useRouter();
  const queryClient = useQueryClient();
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  return (
    <div className="space-y-4">
      {error ? <InlineAlert tone="danger" title={errorMessage(error)} /> : null}
      <Button
        className="w-full"
        loading={busy}
        onClick={async () => {
          setBusy(true);
          setError(null);
          try {
            const r = await api.post<{ organisation_id: string }>("/invitations/accept", { token }, { tenant: false });
            await queryClient.refetchQueries({ queryKey: sessionKey });
            setActiveOrganisationId(r.organisation_id);
            router.replace("/overview");
          } catch (e) {
            setError(e);
            setBusy(false);
          }
        }}
      >
        Join organisation
      </Button>
    </div>
  );
}

function SignOutButton() {
  const queryClient = useQueryClient();
  return (
    <Button
      variant="secondary"
      className="mt-5 w-full"
      onClick={async () => {
        await api.post("/auth/logout", undefined, { tenant: false }).catch(() => null);
        await queryClient.invalidateQueries({ queryKey: sessionKey });
      }}
    >
      Sign out
    </Button>
  );
}

function RegisterFromInvite({ token, email }: { token: string; email: string }) {
  const router = useRouter();
  const queryClient = useQueryClient();
  const [error, setError] = useState<unknown>(null);
  const form = useForm<z.infer<typeof inviteRegisterSchema>>({ resolver: zodResolver(inviteRegisterSchema) });
  const next = `/invite?token=${encodeURIComponent(token)}`;
  return (
    <>
      <form
        noValidate
        className="space-y-5"
        onSubmit={form.handleSubmit(async (v) => {
          setError(null);
          try {
            await api.post("/auth/register", { ...v, email, invitation_token: token }, { tenant: false });
            await api.post("/auth/login", { email, password: v.password }, { tenant: false });
            await queryClient.invalidateQueries({ queryKey: sessionKey });
            router.replace("/overview");
          } catch (e) {
            setError(e);
          }
        })}
      >
        {error ? <InlineAlert tone="danger" title={errorMessage(error)} /> : null}
        <Field label="Email">
          {(p) => <Input {...p} value={email} readOnly disabled />}
        </Field>
        <Field label="Your name" error={form.formState.errors.full_name?.message}>
          {(p) => <Input {...p} {...form.register("full_name")} autoComplete="name" autoFocus />}
        </Field>
        <Field label="Choose a password" hint={`At least ${MIN_PASSWORD} characters.`} error={form.formState.errors.password?.message}>
          {(p) => <Input {...p} {...form.register("password")} type="password" autoComplete="new-password" />}
        </Field>
        <Button type="submit" className="w-full" loading={form.formState.isSubmitting}>
          Create account and join
        </Button>
      </form>
      <p className="mt-8 text-center text-sm text-ink-secondary">
        Already have an Operon account?{" "}
        <Link href={`/login?next=${encodeURIComponent(next)}`} className="font-medium text-ink underline-offset-4 hover:underline">
          Sign in to accept
        </Link>
      </p>
    </>
  );
}
