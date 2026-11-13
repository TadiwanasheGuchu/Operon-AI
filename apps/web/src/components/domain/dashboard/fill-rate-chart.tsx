"use client";

import { Table as TableIcon, ChartLine } from "lucide-react";
import { useState } from "react";
import {
  CartesianGrid,
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip as ChartTooltip,
  XAxis,
  YAxis,
  type TooltipContentProps,
} from "recharts";
import type { NameType, ValueType } from "recharts/types/component/DefaultTooltipContent";

import { ProvenanceBadge } from "@/components/data-display/provenance-badge";
import { Table, TableScroll, Td, Th, Tr } from "@/components/data-display/table";
import { Button } from "@/components/ui/button";
import { Panel, PanelBody, PanelHeader } from "@/components/ui/panel";
import type { FillRate, Period, Provenance } from "@/features/dashboard/contract";
import { formatDate, formatPercent } from "@/lib/format";

import { PERIOD_LABEL } from "./period-control";


export function summariseFillRate({ points, target }: FillRate) {
  const values = points.map((p) => p.value);
  const average = values.reduce((a, b) => a + b, 0) / Math.max(values.length, 1);
  const latest = points.at(-1);
  let daysBelow = 0;
  for (let i = points.length - 1; i >= 0 && points[i].value < target; i--) daysBelow++;
  return { average, latest, daysBelow, min: Math.min(...values) };
}

export function FillRateChart({
  fillRate,
  period,
  provenance,
}: {
  fillRate: FillRate;
  period: Period;
  provenance: Provenance;
}) {
  const [view, setView] = useState<"chart" | "table">("chart");
  const { average, latest, daysBelow } = summariseFillRate(fillRate);
  const summary = `Order fill rate averaged ${formatPercent(average)} over the last ${PERIOD_LABEL[period]}. Latest ${latest ? formatPercent(latest.value) : "unavailable"}${
    daysBelow > 0 ? `, below the ${fillRate.target}% target for the last ${daysBelow} day${daysBelow > 1 ? "s" : ""}` : `, at or above the ${fillRate.target}% target`
  }.`;
  const domainMin = Math.floor(Math.min(fillRate.target - 1, ...fillRate.points.map((p) => p.value)) - 0.5);

  return (
    <Panel aria-labelledby="fill-rate-title">
      <PanelHeader
        id="fill-rate-title"
        title="Order fill rate"
        description="Share of order lines shipped complete from stock, per day"
        actions={
          <>
          <ProvenanceBadge provenance={provenance} />
          <Button
            variant="tertiary"
            size="sm"
            onClick={() => setView((v) => (v === "chart" ? "table" : "chart"))}
            aria-pressed={view === "table"}
          >
            {view === "chart" ? <TableIcon aria-hidden /> : <ChartLine aria-hidden />}
            {view === "chart" ? "View as table" : "View as chart"}
          </Button>
          </>
        }
      />
      <PanelBody>
        <div className="mb-3 flex flex-wrap items-baseline gap-x-6 gap-y-1">
          <p>
            <span className="text-2xl font-semibold tracking-[-0.02em] text-ink">
              {latest ? formatPercent(latest.value) : "—"}
            </span>
            <span className="ml-1.5 text-xs text-ink-muted">latest</span>
          </p>
          <p className="text-[13px] text-ink-secondary">
            Average <span className="font-medium text-ink tnum">{formatPercent(average)}</span>
          </p>
          <p className="text-[13px] text-ink-secondary">
            Target <span className="font-medium text-ink tnum">{fillRate.target}%</span>
          </p>
        </div>
        <p className="sr-only" aria-live="polite">{summary}</p>

        {view === "chart" ? (
          <div className="h-60 w-full" aria-hidden>
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={fillRate.points} margin={{ top: 8, right: 8, bottom: 0, left: -12 }}>
                <CartesianGrid vertical={false} stroke="var(--chart-grid)" strokeWidth={1} />
                <XAxis
                  dataKey="date"
                  tickFormatter={formatDate}
                  tick={{ fill: "var(--text-muted)", fontSize: 11 }}
                  tickLine={false}
                  axisLine={{ stroke: "var(--chart-grid)" }}
                  minTickGap={28}
                />
                <YAxis
                  domain={[domainMin, 100]}
                  tickFormatter={(v: number) => `${v}%`}
                  tick={{ fill: "var(--text-muted)", fontSize: 11 }}
                  tickLine={false}
                  axisLine={false}
                  width={52}
                  allowDecimals={false}
                />
                <ReferenceLine
                  y={fillRate.target}
                  stroke="var(--chart-reference)"
                  strokeDasharray="4 4"
                  label={{
                    value: `Target ${fillRate.target}%`,
                    position: "insideTopRight",
                    fill: "var(--text-muted)",
                    fontSize: 11,
                  }}
                />
                <ChartTooltip
                  content={FillRateTooltip}
                  cursor={{ stroke: "var(--color-steel)", strokeWidth: 1 }}
                />
                <Line
                  type="monotone"
                  dataKey="value"
                  stroke="var(--chart-series)"
                  strokeWidth={2}
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  dot={false}
                  activeDot={{ r: 4, fill: "var(--chart-series)", stroke: "var(--surface-raised)", strokeWidth: 2 }}
                  isAnimationActive={false}
                />
              </LineChart>
            </ResponsiveContainer>
          </div>
        ) : (
          <TableScroll className="-mx-5 max-h-60 overflow-y-auto">
            <Table>
              <caption className="sr-only">{summary}</caption>
              <thead className="sticky top-0 bg-raised">
                <tr>
                  <Th>Date</Th>
                  <Th numeric>Fill rate</Th>
                  <Th numeric>Versus target</Th>
                </tr>
              </thead>
              <tbody>
                {[...fillRate.points].reverse().map((p) => (
                  <Tr key={p.date}>
                    <Td>{formatDate(p.date)}</Td>
                    <Td numeric>{formatPercent(p.value)}</Td>
                    <Td numeric className={p.value < fillRate.target ? "text-danger" : "text-ink-secondary"}>
                      {p.value < fillRate.target ? "Below" : "At or above"}{" "}
                      ({(p.value - fillRate.target > 0 ? "+" : "") + (p.value - fillRate.target).toFixed(1)} pts)
                    </Td>
                  </Tr>
                ))}
              </tbody>
            </Table>
          </TableScroll>
        )}
      </PanelBody>
    </Panel>
  );
}

function FillRateTooltip({ active, payload }: TooltipContentProps<ValueType, NameType>) {
  if (!active || !payload?.length) return null;
  const point = payload[0].payload as { date: string; value: number };
  return (
    <div className="rounded-[8px] border border-line bg-raised px-3 py-2 text-xs shadow-popover">
      <p className="text-ink-muted">{formatDate(point.date)}</p>
      <p className="mt-0.5 font-semibold text-ink tnum">{formatPercent(point.value)} fill rate</p>
    </div>
  );
}
