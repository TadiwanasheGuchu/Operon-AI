import { CircleSlash } from "lucide-react";

import { ProvenanceBadge } from "@/components/data-display/provenance-badge";
import { Panel, PanelHeader } from "@/components/ui/panel";
import type { Arrangement } from "@/features/dashboard/arrange";

/** One compact panel instead of many empty ones: what isn't here yet, and why. */
export function NotAvailable({ items }: { items: Arrangement["unavailable"] }) {
  return (
    <Panel aria-labelledby="unavailable-title">
      <PanelHeader
        id="unavailable-title"
        title="Not available yet"
        description="These parts of the overview need connected systems or modules that aren't set up in this organisation."
        actions={<ProvenanceBadge provenance="unavailable" />}
      />
      <ul className="grid gap-px border-t border-line bg-line sm:grid-cols-2 lg:grid-cols-3">
        {items.map((i) => (
          <li key={i.key} className="flex gap-3 bg-raised px-5 py-3.5">
            <CircleSlash className="mt-0.5 size-4 shrink-0 text-icon" aria-hidden />
            <div>
              <p className="text-[13px] font-medium text-ink-secondary">{i.title}</p>
              <p className="text-xs text-ink-muted">{i.message}</p>
            </div>
          </li>
        ))}
      </ul>
    </Panel>
  );
}
