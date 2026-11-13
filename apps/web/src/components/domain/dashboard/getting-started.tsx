import { Circle, CircleCheck } from "lucide-react";
import Link from "next/link";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Panel, PanelHeader } from "@/components/ui/panel";
import type { SetupStep } from "@/features/dashboard/contract";
import { cn } from "@/lib/cn";

export function GettingStarted({ steps }: { steps: SetupStep[] }) {
  const done = steps.filter((s) => s.done).length;
  return (
    <Panel aria-labelledby="setup-title">
      <PanelHeader
        id="setup-title"
        title="Set up your workspace"
        description={`${done} of ${steps.length} done. A few steps before Operon can monitor your operations.`}
      />
      <ol className="divide-y divide-line border-t border-line">
        {steps.map((s) => (
          <li key={s.key} className="flex items-start gap-4 px-5 py-4">
            {s.done ? (
              <CircleCheck className="mt-0.5 size-5 shrink-0 text-success" aria-label="Done" />
            ) : (
              <Circle className="mt-0.5 size-5 shrink-0 text-line-control" aria-label="Not done" />
            )}
            <div className="min-w-0 flex-1">
              <p className={cn("text-sm font-medium", s.done ? "text-ink-secondary" : "text-ink")}>{s.title}</p>
              <p className="mt-0.5 text-[13px] text-ink-muted">{s.body}</p>
            </div>
            {s.done ? null : s.href && s.available ? (
              <Button asChild size="sm" variant="secondary">
                <Link href={s.href}>{s.action_label}</Link>
              </Button>
            ) : !s.href ? (
              <Badge>Not available yet</Badge>
            ) : null}
          </li>
        ))}
      </ol>
    </Panel>
  );
}
