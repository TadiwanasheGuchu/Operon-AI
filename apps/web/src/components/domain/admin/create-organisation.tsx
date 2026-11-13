"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useQueryClient } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";

import { OperonWordmark } from "@/components/brand/operon-mark";
import { InlineAlert } from "@/components/feedback/inline-alert";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogTitle } from "@/components/ui/dialog";
import { Field, Input } from "@/components/ui/form";
import { setActiveOrganisationId } from "@/features/session/active-organisation";
import { sessionKey } from "@/features/session/use-session";
import { api, errorMessage } from "@/lib/api/client";

const schema = z.object({ name: z.string().trim().min(1, "Enter a name.").max(200) });

function CreateOrganisationForm({ onDone, autoFocus }: { onDone?: () => void; autoFocus?: boolean }) {
  const router = useRouter();
  const queryClient = useQueryClient();
  const [error, setError] = useState<unknown>(null);
  const form = useForm<z.infer<typeof schema>>({ resolver: zodResolver(schema) });
  return (
    <form
      noValidate
      className="space-y-5"
      onSubmit={form.handleSubmit(async (v) => {
        setError(null);
        try {
          const org = await api.post<{ id: string }>("/organisations", v, { tenant: false });
          // Refresh memberships first, so the new organisation is known before switching to it.
          await queryClient.refetchQueries({ queryKey: sessionKey });
          queryClient.removeQueries({ predicate: (q) => q.queryKey[0] === "tenant" });
          setActiveOrganisationId(org.id);
          onDone?.();
          router.push("/overview");
        } catch (e) {
          setError(e);
        }
      })}
    >
      {error ? <InlineAlert tone="danger" title={errorMessage(error)} /> : null}
      <Field label="Organisation name" error={form.formState.errors.name?.message}>
        {(p) => <Input {...p} {...form.register("name")} autoComplete="organization" autoFocus={autoFocus} />}
      </Field>
      <Button type="submit" className="w-full" loading={form.formState.isSubmitting}>
        Create organisation
      </Button>
    </form>
  );
}

export function CreateOrganisationDialog({ open, onOpenChange }: { open: boolean; onOpenChange: (o: boolean) => void }) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="p-6">
        <DialogTitle className="text-base font-semibold text-ink">Create an organisation</DialogTitle>
        <DialogDescription className="mt-1 mb-5 text-[13px] text-ink-muted">
          A separate workspace with its own members, data and settings. You&apos;ll be its owner.
        </DialogDescription>
        <CreateOrganisationForm onDone={() => onOpenChange(false)} autoFocus />
      </DialogContent>
    </Dialog>
  );
}

/** Shown when a signed-in user belongs to no organisation (e.g. after being removed). */
export function CreateOrganisationScreen({ first }: { first?: boolean }) {
  return (
    <main className="flex min-h-dvh flex-col bg-canvas px-4 py-8 sm:px-8">
      <OperonWordmark className="text-ink" />
      <div className="mx-auto flex w-full max-w-[400px] flex-1 flex-col justify-center py-10">
        <h1 className="font-display text-[30px] leading-9 text-ink">
          {first ? "You're not in an organisation" : "Create an organisation"}
        </h1>
        <p className="mt-2 mb-7 text-sm text-ink-secondary">
          Create one to get started, or ask an administrator to invite you to theirs.
        </p>
        <CreateOrganisationForm autoFocus />
      </div>
    </main>
  );
}
