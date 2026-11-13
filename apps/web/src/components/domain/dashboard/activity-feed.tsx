import { Cog, Plug, User, Bot, type LucideIcon } from "lucide-react";

import { ProvenanceBadge } from "@/components/data-display/provenance-badge";
import { Panel, PanelHeader } from "@/components/ui/panel";
import type { ActivityEvent, Provenance } from "@/features/dashboard/contract";
import { formatRelative, formatTime } from "@/lib/format";

const ACTOR_ICON: Record<ActivityEvent["actor_type"], LucideIcon> = {
  system: Cog,
  integration: Plug,
  user: User,
  agent: Bot,
};

export function ActivityFeed({ events, provenance }: { events: ActivityEvent[]; provenance: Provenance }) {
  return (
    <Panel aria-labelledby="activity-title">
      <PanelHeader id="activity-title" title="Recent activity" actions={<ProvenanceBadge provenance={provenance} />} />
      {events.length === 0 ? (
        <p className="border-t border-line px-5 py-6 text-center text-[13px] text-ink-muted">No activity yet.</p>
      ) : null}
      <ol className="border-t border-line px-5 py-2 empty:hidden">
        {events.map((e) => {
          const Icon = ACTOR_ICON[e.actor_type];
          return (
            <li key={e.id} className="flex gap-3 py-2.5">
              <span className="mt-0.5 inline-flex size-6 shrink-0 items-center justify-center rounded-full bg-sunken">
                <Icon className="size-3.5 text-ink-secondary" aria-hidden />
              </span>
              <div className="min-w-0 flex-1">
                <p className="text-[13px] text-ink">
                  <span className="font-medium">{e.actor}</span>{" "}
                  <span className="text-ink-secondary">{e.message.charAt(0).toLowerCase() + e.message.slice(1)}</span>
                  {e.ref ? <span className="ml-1 font-mono text-[11px] text-ink-muted">{e.ref}</span> : null}
                </p>
                <p className="mt-0.5 font-mono text-[11px] text-ink-muted">
                  <time dateTime={e.at} title={formatRelative(e.at)}>{formatTime(e.at)}</time> · {e.actor_type}
                </p>
              </div>
            </li>
          );
        })}
      </ol>
    </Panel>
  );
}
