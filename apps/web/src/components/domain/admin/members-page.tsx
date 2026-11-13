"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { MailPlus, UserMinus } from "lucide-react";
import { useState } from "react";
import { useForm, useWatch } from "react-hook-form";
import { z } from "zod";

import { Table, TableScroll, Td, Th, Tr } from "@/components/data-display/table";
import { ConfirmDialog } from "@/components/feedback/confirm-dialog";
import { InlineAlert } from "@/components/feedback/inline-alert";
import { EmptyState, ErrorState, PermissionDenied } from "@/components/feedback/states";
import { useToast } from "@/components/feedback/toast";
import { MoreIcon } from "@/components/icons";
import { PageContainer, PageHeader } from "@/components/layout/page-header";
import { Badge, StatusBadge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogTitle } from "@/components/ui/dialog";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Field, Input, Select } from "@/components/ui/form";
import { Panel, PanelHeader } from "@/components/ui/panel";
import { Skeleton } from "@/components/ui/skeleton";
import {
  type Member,
  type Role,
  useInvitations,
  useMembers,
  useRoles,
  useTenantMutation,
} from "@/features/admin/api";
import { useWorkspace } from "@/features/workspace/workspace-context";
import { api, ApiRequestError, errorMessage } from "@/lib/api/client";
import { formatDate } from "@/lib/format";

export function MembersPage() {
  const { workspace } = useWorkspace();
  const canInvite = workspace.can("members.invite");
  const canManage = workspace.can("members.manage");
  const members = useMembers();
  const invitations = useInvitations();
  const roles = useRoles(workspace.can("roles.read"));
  const [inviting, setInviting] = useState(false);

  if (members.error instanceof ApiRequestError && members.error.status === 403) {
    return (
      <PageContainer>
        <PermissionDenied permission="members.read" />
      </PageContainer>
    );
  }

  return (
    <PageContainer>
      <PageHeader
        title="Members"
        description={`People with access to ${workspace.organisation.name}, and what they can do.`}
        actions={
          canInvite ? (
            <Button onClick={() => setInviting(true)}>
              <MailPlus aria-hidden /> Invite people
            </Button>
          ) : null
        }
      />

      <Panel className="mt-6" aria-labelledby="members-title">
        <PanelHeader
          id="members-title"
          title="Members"
          description={members.data ? `${members.data.length} ${members.data.length === 1 ? "person" : "people"}` : undefined}
        />
        {members.isPending ? (
          <TableSkeleton />
        ) : members.isError ? (
          <ErrorState compact onRetry={() => members.refetch()} requestId={(members.error as ApiRequestError).requestId} />
        ) : (
          <TableScroll className="border-t border-line">
            <Table>
              <thead>
                <tr>
                  <Th>Name</Th>
                  <Th>Role</Th>
                  <Th>Two-factor</Th>
                  <Th>Joined</Th>
                  <Th className="w-12">
                    <span className="sr-only">Actions</span>
                  </Th>
                </tr>
              </thead>
              <tbody>
                {members.data.map((m) => (
                  <MemberRow key={m.id} member={m} roles={roles.data ?? []} canManage={canManage} />
                ))}
              </tbody>
            </Table>
          </TableScroll>
        )}
      </Panel>

      <PendingInvitations canInvite={canInvite} invitations={invitations} />

      {canInvite ? <InviteDialog open={inviting} onOpenChange={setInviting} roles={roles.data ?? []} /> : null}
    </PageContainer>
  );
}

function MemberRow({ member, roles, canManage }: { member: Member; roles: Role[]; canManage: boolean }) {
  const toast = useToast();
  const [removing, setRemoving] = useState(false);
  const target = roles.find((r) => r.key === member.role_key);
  const manageable = canManage && !member.is_you && Boolean(target?.assignable_by_you);
  const changeRole = useTenantMutation(
    (role_key: string) => api.patch<Member>(`/members/${member.id}`, { role_key }),
    ["members", "audit"],
  );
  const remove = useTenantMutation(() => api.delete(`/members/${member.id}`), ["members", "audit"]);

  return (
    <Tr>
      <Td>
        <div className="min-w-48">
          <p className="font-medium text-ink">
            {member.full_name} {member.is_you ? <Badge className="ml-1">You</Badge> : null}
          </p>
          <p className="text-xs text-ink-muted">{member.email}</p>
        </div>
      </Td>
      <Td>
        {manageable ? (
          <Select
            aria-label={`Role for ${member.full_name}`}
            className="h-8 w-48 text-[13px]"
            value={member.role_key}
            disabled={changeRole.isPending}
            onChange={(e) => {
              const role = roles.find((r) => r.key === e.target.value);
              changeRole.mutate(e.target.value, {
                onSuccess: () => toast({ tone: "success", title: `${member.full_name} is now ${role?.name ?? e.target.value}` }),
                onError: (err) => toast({ tone: "danger", title: "Role not changed", description: errorMessage(err) }),
              });
            }}
          >
            {roles.filter((r) => r.assignable_by_you).map((r) => (
              <option key={r.key} value={r.key}>
                {r.name}
              </option>
            ))}
          </Select>
        ) : (
          <span className="text-ink-secondary">{member.role_name}</span>
        )}
      </Td>
      <Td>{member.mfa_enabled ? <StatusBadge status="healthy" label="On" /> : <StatusBadge status="paused" label="Off" />}</Td>
      <Td className="whitespace-nowrap text-ink-secondary">{formatDate(member.joined_at)}</Td>
      <Td>
        {manageable ? (
          <>
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <Button variant="quiet" size="icon-sm" aria-label={`Actions for ${member.full_name}`}>
                  <MoreIcon aria-hidden />
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent>
                <DropdownMenuItem className="text-danger [&_svg]:text-danger" onSelect={() => setRemoving(true)}>
                  <UserMinus aria-hidden /> Remove from organisation
                </DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
            <ConfirmDialog
              open={removing}
              onOpenChange={setRemoving}
              destructive
              title={`Remove ${member.full_name}?`}
              description={`${member.full_name} will lose access to this organisation immediately. Their account and other organisations are not affected.`}
              confirmLabel="Remove member"
              onConfirm={async () => {
                try {
                  await remove.mutateAsync(undefined);
                  toast({ tone: "success", title: `${member.full_name} was removed` });
                } catch (err) {
                  toast({ tone: "danger", title: "Member not removed", description: errorMessage(err) });
                }
              }}
            />
          </>
        ) : null}
      </Td>
    </Tr>
  );
}

function PendingInvitations({ canInvite, invitations }: { canInvite: boolean; invitations: ReturnType<typeof useInvitations> }) {
  const toast = useToast();
  const revoke = useTenantMutation((id: string) => api.delete(`/invitations/${id}`), ["invitations", "audit"]);
  return (
    <Panel className="mt-5" aria-labelledby="invitations-title">
      <PanelHeader id="invitations-title" title="Pending invitations" description="Invitations expire after 7 days." />
      {invitations.isPending ? (
        <TableSkeleton rows={1} />
      ) : invitations.isError ? (
        <ErrorState compact onRetry={() => invitations.refetch()} />
      ) : invitations.data.length === 0 ? (
        <EmptyState compact title="No pending invitations" description={canInvite ? "People you invite appear here until they join." : undefined} />
      ) : (
        <TableScroll className="border-t border-line">
          <Table>
            <thead>
              <tr>
                <Th>Email</Th>
                <Th>Role</Th>
                <Th>Invited by</Th>
                <Th>Expires</Th>
                <Th className="w-24">
                  <span className="sr-only">Actions</span>
                </Th>
              </tr>
            </thead>
            <tbody>
              {invitations.data.map((i) => (
                <Tr key={i.id}>
                  <Td className="font-medium">{i.email}</Td>
                  <Td className="text-ink-secondary">{i.role_name}</Td>
                  <Td className="text-ink-secondary">{i.invited_by ?? "—"}</Td>
                  <Td className="whitespace-nowrap text-ink-secondary">{formatDate(i.expires_at)}</Td>
                  <Td className="text-right">
                    {canInvite ? (
                      <Button
                        size="sm"
                        variant="tertiary"
                        loading={revoke.isPending && revoke.variables === i.id}
                        onClick={() =>
                          revoke.mutate(i.id, {
                            onSuccess: () => toast({ tone: "success", title: `Invitation to ${i.email} withdrawn` }),
                            onError: (err) => toast({ tone: "danger", title: "Not withdrawn", description: errorMessage(err) }),
                          })
                        }
                      >
                        Withdraw
                      </Button>
                    ) : null}
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

const inviteSchema = z.object({
  email: z.string().trim().toLowerCase().pipe(z.email("Enter a valid email address.")),
  role_key: z.string().min(1, "Choose a role."),
});

function InviteDialog({ open, onOpenChange, roles }: { open: boolean; onOpenChange: (o: boolean) => void; roles: Role[] }) {
  const toast = useToast();
  const assignable = roles.filter((r) => r.assignable_by_you);
  const [error, setError] = useState<unknown>(null);
  const form = useForm<z.infer<typeof inviteSchema>>({
    resolver: zodResolver(inviteSchema),
    defaultValues: { email: "", role_key: "viewer" },
  });
  const invite = useTenantMutation((v: z.infer<typeof inviteSchema>) => api.post("/invitations", v), ["invitations", "audit"]);
  const roleKey = useWatch({ control: form.control, name: "role_key" });
  const selected = roles.find((r) => r.key === roleKey);

  return (
    <Dialog
      open={open}
      onOpenChange={(o) => {
        onOpenChange(o);
        if (!o) {
          form.reset();
          setError(null);
        }
      }}
    >
      <DialogContent className="p-6">
        <DialogTitle className="text-base font-semibold text-ink">Invite someone</DialogTitle>
        <DialogDescription className="mt-1 mb-5 text-[13px] text-ink-muted">
          They&apos;ll get an email with a link to join. You can only invite people to roles at or below your own.
        </DialogDescription>
        <form
          noValidate
          className="space-y-5"
          onSubmit={form.handleSubmit(async (v) => {
            setError(null);
            try {
              await invite.mutateAsync(v);
              toast({ tone: "success", title: `Invitation sent to ${v.email}` });
              onOpenChange(false);
              form.reset();
            } catch (e) {
              setError(e);
            }
          })}
        >
          {error ? <InlineAlert tone="danger" title={errorMessage(error)} /> : null}
          <Field label="Email" error={form.formState.errors.email?.message}>
            {(p) => <Input {...p} {...form.register("email")} type="email" autoComplete="off" autoFocus />}
          </Field>
          <Field label="Role" hint={selected?.description} error={form.formState.errors.role_key?.message}>
            {(p) => (
              <Select {...p} {...form.register("role_key")}>
                {assignable.map((r) => (
                  <option key={r.key} value={r.key}>
                    {r.name}
                  </option>
                ))}
              </Select>
            )}
          </Field>
          <div className="flex justify-end gap-2 pt-1">
            <Button type="button" variant="secondary" onClick={() => onOpenChange(false)}>
              Cancel
            </Button>
            <Button type="submit" loading={form.formState.isSubmitting}>
              Send invitation
            </Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  );
}

function TableSkeleton({ rows = 3 }: { rows?: number }) {
  return (
    <div role="status" aria-label="Loading" className="space-y-3 border-t border-line px-5 py-4">
      {Array.from({ length: rows }, (_, i) => (
        <Skeleton key={i} className="h-9 w-full" />
      ))}
    </div>
  );
}
