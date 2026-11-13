"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";

import { InlineAlert } from "@/components/feedback/inline-alert";
import { useToast } from "@/components/feedback/toast";
import { PageContainer, PageHeader } from "@/components/layout/page-header";
import { Button } from "@/components/ui/button";
import { Field, Input } from "@/components/ui/form";
import { Panel, PanelBody, PanelHeader } from "@/components/ui/panel";
import { sessionKey } from "@/features/session/use-session";
import { useWorkspace } from "@/features/workspace/workspace-context";
import { api, errorMessage } from "@/lib/api/client";

const schema = z.object({ full_name: z.string().trim().min(1, "Enter your name.").max(200) });

export function ProfilePage() {
  const { workspace } = useWorkspace();
  const toast = useToast();
  const queryClient = useQueryClient();
  const [error, setError] = useState<unknown>(null);
  const form = useForm<z.infer<typeof schema>>({
    resolver: zodResolver(schema),
    defaultValues: { full_name: workspace.user?.name ?? "" },
  });
  return (
    <PageContainer narrow>
      <PageHeader title="Profile" description="How you appear to others in your organisations." />
      <Panel className="mt-6" aria-labelledby="profile-title">
        <PanelHeader id="profile-title" title="Your details" />
        <PanelBody>
          <form
            noValidate
            className="space-y-4"
            onSubmit={form.handleSubmit(async (v) => {
              setError(null);
              try {
                await api.patch("/users/me", v, { tenant: false });
                await queryClient.invalidateQueries({ queryKey: sessionKey });
                form.reset(v);
                toast({ tone: "success", title: "Profile saved" });
              } catch (e) {
                setError(e);
              }
            })}
          >
            {error ? <InlineAlert tone="danger" title={errorMessage(error)} /> : null}
            <Field label="Full name" error={form.formState.errors.full_name?.message}>
              {(p) => <Input {...p} {...form.register("full_name")} autoComplete="name" />}
            </Field>
            <Field label="Email" hint="Your sign-in address. Changing it isn't available yet.">
              {(p) => <Input {...p} value={workspace.user?.email ?? ""} readOnly disabled />}
            </Field>
            <Button type="submit" loading={form.formState.isSubmitting} disabled={!form.formState.isDirty}>
              Save changes
            </Button>
          </form>
        </PanelBody>
      </Panel>
    </PageContainer>
  );
}
