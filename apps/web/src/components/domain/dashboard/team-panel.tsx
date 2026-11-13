import Link from "next/link";

import { ProvenanceBadge } from "@/components/data-display/provenance-badge";
import { Panel, PanelHeader } from "@/components/ui/panel";
import type { Provenance, Team } from "@/features/dashboard/contract";
import { formatRelative } from "@/lib/format";

export function TeamPanel({ team, provenance }: { team: Team; provenance: Provenance }) {
  const coverage = team.members ? Math.round((team.mfa_enabled / team.members) * 100) : 0;
  return (
    <Panel aria-labelledby="team-title">
      <PanelHeader
        id="team-title"
        title="Team"
        actions={<ProvenanceBadge provenance={provenance} />}
      />
      <dl className="grid grid-cols-3 border-t border-line text-center">
        {[
          ["Members", team.members],
          ["Invited", team.pending_invitations],
          ["Two-factor", `${coverage}%`],
        ].map(([label, value]) => (
          <div key={label} className="border-line px-3 py-3 not-last:border-r">
            <dt className="text-xs text-ink-muted">{label}</dt>
            <dd className="mt-0.5 text-lg font-semibold text-ink">{value}</dd>
          </div>
        ))}
      </dl>
      <div className="border-t border-line px-5 py-3">
        <p className="text-xs font-medium text-ink-muted">Recently joined</p>
        <ul className="mt-2 space-y-1.5">
          {team.recent_joins.map((j) => (
            <li key={`${j.name}-${j.joined_at}`} className="flex items-baseline justify-between gap-3 text-[13px]">
              <span className="min-w-0 truncate text-ink">
                {j.name} <span className="text-ink-muted">· {j.role_name}</span>
              </span>
              <time dateTime={j.joined_at} className="shrink-0 font-mono text-[11px] text-ink-muted">
                {formatRelative(j.joined_at)}
              </time>
            </li>
          ))}
        </ul>
        <Link href="/admin/members" className="mt-3 inline-block text-[13px] text-ink-secondary underline-offset-4 hover:text-ink hover:underline">
          Manage members
        </Link>
      </div>
    </Panel>
  );
}
