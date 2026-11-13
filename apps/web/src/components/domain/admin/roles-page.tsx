"use client";

import { Check, Minus } from "lucide-react";

import { Table, TableScroll, Td, Th, Tr } from "@/components/data-display/table";
import { ErrorState, PermissionDenied } from "@/components/feedback/states";
import { PageContainer, PageHeader } from "@/components/layout/page-header";
import { Panel } from "@/components/ui/panel";
import { Skeleton } from "@/components/ui/skeleton";
import { usePermissionCatalogue, useRoles } from "@/features/admin/api";
import { useWorkspace } from "@/features/workspace/workspace-context";

export function RolesPage() {
  const { workspace } = useWorkspace();
  const allowed = workspace.can("roles.read");
  const roles = useRoles(allowed);
  const catalogue = usePermissionCatalogue();

  if (!allowed) {
    return (
      <PageContainer>
        <PermissionDenied permission="roles.read" />
      </PageContainer>
    );
  }
  return (
    <PageContainer>
      <PageHeader
        title="Roles"
        description="What each role can do in this organisation. System roles are fixed for now; custom roles come later."
      />
      <Panel className="mt-6">
        {roles.isPending || catalogue.isPending ? (
          <div role="status" aria-label="Loading roles" className="space-y-3 p-5">
            <Skeleton className="h-8 w-full" />
            <Skeleton className="h-40 w-full" />
          </div>
        ) : roles.isError || catalogue.isError ? (
          <ErrorState compact onRetry={() => void Promise.all([roles.refetch(), catalogue.refetch()])} />
        ) : (
          <TableScroll>
            <Table>
              <caption className="sr-only">Permissions granted to each role</caption>
              <thead>
                <tr>
                  <Th className="min-w-64">Permission</Th>
                  {roles.data.map((r) => (
                    <Th key={r.key} className="text-center whitespace-normal">
                      {r.name}
                    </Th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {catalogue.data.map((p) => (
                  <Tr key={p.key}>
                    <Td>
                      <p className="text-ink">{p.description}</p>
                      <p className="font-mono text-[11px] text-ink-muted">{p.key}</p>
                    </Td>
                    {roles.data.map((r) => {
                      const granted = r.permissions.includes(p.key);
                      return (
                        <Td key={r.key} className="text-center">
                          {granted ? (
                            <Check className="mx-auto size-4 text-success" aria-label="Granted" />
                          ) : (
                            <Minus className="mx-auto size-4 text-line-control" aria-label="Not granted" />
                          )}
                        </Td>
                      );
                    })}
                  </Tr>
                ))}
              </tbody>
            </Table>
          </TableScroll>
        )}
      </Panel>
      {roles.data ? (
        <dl className="mt-5 grid gap-x-6 gap-y-3 sm:grid-cols-2 lg:grid-cols-3">
          {roles.data.map((r) => (
            <div key={r.key}>
              <dt className="text-[13px] font-medium text-ink">{r.name}</dt>
              <dd className="text-[13px] text-ink-muted">{r.description}</dd>
            </div>
          ))}
        </dl>
      ) : null}
    </PageContainer>
  );
}
