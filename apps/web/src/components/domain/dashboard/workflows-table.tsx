import { ProvenanceBadge } from "@/components/data-display/provenance-badge";
import { Table, TableScroll, Td, Th, Tr } from "@/components/data-display/table";
import { StatusBadge } from "@/components/ui/badge";
import { Panel, PanelHeader } from "@/components/ui/panel";
import type { Provenance, WorkflowStatus } from "@/features/dashboard/contract";
import { formatPercent } from "@/lib/format";

export function WorkflowsTable({ workflows, provenance }: { workflows: WorkflowStatus[]; provenance: Provenance }) {
  return (
    <Panel aria-labelledby="workflows-title">
      <PanelHeader
        id="workflows-title"
        title="Workflow execution"
        description="Current state of automated processes"
        actions={<ProvenanceBadge provenance={provenance} />}
      />
      <TableScroll className="border-t border-line">
        <Table>
          <thead>
            <tr>
              <Th>Workflow</Th>
              <Th>Status</Th>
              <Th numeric>Running</Th>
              <Th numeric>Awaiting</Th>
              <Th numeric>Failed, 24 h</Th>
              <Th numeric>Success, 30 d</Th>
            </tr>
          </thead>
          <tbody>
            {workflows.map((w) => (
              <Tr key={w.workflow}>
                <Td className="font-medium whitespace-nowrap">{w.workflow}</Td>
                <Td>
                  {w.failed_24h > 0 ? (
                    <StatusBadge status="attention" label={`${w.failed_24h} failed`} />
                  ) : w.awaiting_approval > 0 ? (
                    <StatusBadge status="pending" label="Awaiting approval" />
                  ) : (
                    <StatusBadge status="healthy" />
                  )}
                </Td>
                <Td numeric>{w.running}</Td>
                <Td numeric>{w.awaiting_approval}</Td>
                <Td numeric className={w.failed_24h ? "font-medium text-danger" : undefined}>
                  {w.failed_24h}
                </Td>
                <Td numeric>{formatPercent(w.success_rate)}</Td>
              </Tr>
            ))}
          </tbody>
        </Table>
      </TableScroll>
    </Panel>
  );
}
