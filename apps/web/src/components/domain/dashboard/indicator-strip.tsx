import { CircleCheck, CircleSlash, CircleX, TriangleAlert } from "lucide-react";

import { Delta } from "@/components/data-display/delta";
import type { Indicator, Period } from "@/features/dashboard/contract";
import { cn } from "@/lib/cn";

import { PERIOD_PREVIOUS } from "./period-control";

const STATE = {
  healthy: { icon: CircleCheck, className: "text-success", label: "Healthy" },
  attention: { icon: TriangleAlert, className: "text-warning", label: "Needs attention" },
  critical: { icon: CircleX, className: "text-danger", label: "Critical" },
  neutral: { icon: null, className: "", label: "" },
} as const;

/**
 * Operational summary as one composed strip. An unavailable indicator shows a muted dash and
 * why, never a zero that could be mistaken for a real value.
 */
export function IndicatorStrip({ indicators, period }: { indicators: Indicator[]; period: Period }) {
  const cols = indicators.length >= 5 ? "xl:grid-cols-5" : indicators.length === 4 ? "xl:grid-cols-4" : "xl:grid-cols-3";
  return (
    <section aria-label="Operational summary" className="rounded-panel border border-line bg-raised">
      <dl className={cn("grid grid-cols-2 divide-line sm:grid-cols-3 xl:divide-x", cols)}>
        {indicators.map((ind, i) => {
          const unavailable = ind.provenance === "unavailable" || ind.value === null;
          const state = STATE[ind.state];
          const Icon = unavailable ? CircleSlash : state.icon;
          return (
            <div
              key={ind.key}
              className={cn(
                "flex flex-col gap-1 border-line px-5 py-4 max-xl:border-b",
                i === indicators.length - 1 && indicators.length % 2 === 1 && "col-span-2 sm:col-span-1",
                i === indicators.length - 1 && "max-xl:border-b-0",
              )}
            >
              <dt className="flex items-center gap-1.5 text-[13px] text-ink-secondary">
                {Icon ? <Icon className={cn("size-3.5", unavailable ? "text-icon" : state.className)} aria-hidden /> : null}
                {ind.label}
                {unavailable ? <span className="sr-only"> (not available yet)</span> : Icon ? <span className="sr-only"> ({state.label})</span> : null}
              </dt>
              <dd className="flex items-baseline gap-1.5">
                {unavailable ? (
                  <span className="text-[28px] leading-9 font-semibold text-line-control" aria-hidden>
                    —
                  </span>
                ) : (
                  <>
                    <span className="text-[28px] leading-9 font-semibold tracking-[-0.02em] text-ink">{ind.value}</span>
                    {ind.total !== null ? <span className="text-sm text-ink-muted">of {ind.total}</span> : null}
                  </>
                )}
              </dd>
              <dd className="text-xs text-ink-muted">{ind.detail}</dd>
              <dd className="min-h-4">
                {unavailable || ind.value === null ? null : (
                  <Delta
                    value={ind.value}
                    previous={ind.previous_value}
                    increaseIs={ind.increase_is}
                    periodLabel={PERIOD_PREVIOUS[period]}
                  />
                )}
              </dd>
            </div>
          );
        })}
      </dl>
    </section>
  );
}
