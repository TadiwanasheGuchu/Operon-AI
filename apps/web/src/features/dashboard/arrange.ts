import type { DashboardSummary, SectionKey } from "./contract";

export const SECTION_TITLES: Record<SectionKey, string> = {
  getting_started: "Set up your workspace",
  insights: "Priority exceptions",
  approvals: "Pending approvals",
  incidents: "Active incidents",
  fill_rate: "Order fill rate",
  inventory_risk: "Stock at or below reorder point",
  workflows: "Workflow execution",
  integrations: "Integration status",
  activity: "Recent activity",
  team: "Team",
};

export interface Placement {
  key: SectionKey;
  size: "wide" | "narrow";
}

export interface Arrangement {
  panels: Placement[];
  unavailable: { key: SectionKey; title: string; message: string }[];
}

/**
 * Decide what the overview renders, in layout order:
 * ready sections become panels; unavailable ones collapse into a single "not available yet" list;
 * restricted ones are omitted; a completed (or empty) setup checklist is hidden.
 */
export function arrange(summary: DashboardSummary): Arrangement {
  const panels: Placement[] = [];
  const unavailable: Arrangement["unavailable"] = [];
  for (const { key, size } of summary.layout.sections) {
    const section = summary[key];
    if (section.state === "restricted") continue;
    if (section.state === "unavailable") {
      unavailable.push({ key, title: SECTION_TITLES[key], message: section.message ?? "Not available yet." });
      continue;
    }
    if (key === "getting_started") {
      const steps = summary.getting_started.data ?? [];
      if (steps.length === 0 || steps.every((s) => s.done)) continue;
    }
    panels.push({ key, size });
  }
  return { panels, unavailable };
}
