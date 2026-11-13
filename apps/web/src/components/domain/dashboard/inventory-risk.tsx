import { ProvenanceBadge } from "@/components/data-display/provenance-badge";
import { Panel, PanelBody, PanelHeader } from "@/components/ui/panel";
import type { LocationRisk, Provenance } from "@/features/dashboard/contract";
import { formatNumber } from "@/lib/format";

/** Single-series horizontal bars, directly labelled, so no tooltip or legend is needed. */
export function InventoryRisk({ rows, provenance }: { rows: LocationRisk[]; provenance: Provenance }) {
  const max = Math.max(...rows.map((r) => r.skus_at_risk), 1);
  const total = rows.reduce((s, r) => s + r.skus_at_risk, 0);
  return (
    <Panel aria-labelledby="inventory-risk-title">
      <PanelHeader
        id="inventory-risk-title"
        title="Stock at or below reorder point"
        description={`${total} SKUs across ${rows.length} locations`}
        actions={<ProvenanceBadge provenance={provenance} />}
      />
      <PanelBody>
        <table className="w-full text-[13px]">
          <caption className="sr-only">SKUs at or below reorder point, by location</caption>
          <thead className="sr-only">
            <tr>
              <th scope="col">Location</th>
              <th scope="col">SKUs at risk</th>
              <th scope="col">SKUs tracked</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.location} className="align-middle">
                <th scope="row" className="w-[42%] py-2 pr-3 text-left font-normal text-ink-secondary">
                  {r.location}
                </th>
                <td className="py-2">
                  <div className="flex items-center gap-2">
                    <div className="h-3 flex-1">
                      <div
                        className="h-3 rounded-r-[4px] bg-[var(--chart-series)]"
                        style={{ width: `${Math.max((r.skus_at_risk / max) * 100, 2)}%` }}
                      />
                    </div>
                    <span className="w-6 text-right font-medium text-ink tnum">{r.skus_at_risk}</span>
                  </div>
                </td>
                <td className="hidden w-20 py-2 pl-3 text-right text-xs text-ink-muted tnum sm:table-cell">
                  of {formatNumber(r.skus_tracked)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </PanelBody>
    </Panel>
  );
}
