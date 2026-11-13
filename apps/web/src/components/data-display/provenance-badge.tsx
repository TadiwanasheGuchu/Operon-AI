import { CircleSlash, Clock, FlaskConical, Radio, type LucideIcon } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import type { Provenance } from "@/features/dashboard/contract";

const PROVENANCE: Record<
  Provenance,
  { label: string; tone: "success" | "warning" | "info" | "neutral"; icon: LucideIcon; hint: string }
> = {
  live: { label: "Live", tone: "success", icon: Radio, hint: "From connected systems" },
  demo: { label: "Demo data", tone: "info", icon: FlaskConical, hint: "Fictional sample data" },
  stale: { label: "Stale", tone: "warning", icon: Clock, hint: "Last synchronisation is overdue" },
  unavailable: { label: "Unavailable", tone: "neutral", icon: CircleSlash, hint: "Source not connected" },
};

/** Every number on screen states where it came from. */
export function ProvenanceBadge({ provenance }: { provenance: Provenance }) {
  const p = PROVENANCE[provenance];
  return (
    <Badge tone={p.tone} icon={p.icon}>
      <span>{p.label}</span>
      <span className="sr-only"> — {p.hint}</span>
    </Badge>
  );
}
