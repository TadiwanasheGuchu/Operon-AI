"use client";

import { LayoutPanelTop } from "lucide-react";

import { useToast } from "@/components/feedback/toast";
import { Select } from "@/components/ui/form";
import { useLayoutSettings, useSetLayout } from "@/features/dashboard/use-dashboard-summary";
import { errorMessage } from "@/lib/api/client";

/** Choose an overview layout. Saved per user and organisation; "role default" clears the choice. */
export function LayoutControl() {
  const settings = useLayoutSettings();
  const setLayout = useSetLayout();
  const toast = useToast();
  if (!settings.data) return null;
  const { current, presets, default_preset } = settings.data;
  const defaultName = presets.find((p) => p.key === default_preset)?.name ?? default_preset;
  return (
    <label className="relative inline-flex items-center" title="Overview layout. The default comes from your role.">
      <span className="sr-only">Overview layout</span>
      <LayoutPanelTop className="pointer-events-none absolute left-2.5 size-4 text-icon" aria-hidden />
      <Select
        className="h-9 w-52 pl-8 text-[13px]"
        value={current.is_default ? "" : current.preset}
        disabled={setLayout.isPending}
        onChange={(e) =>
          setLayout.mutate(e.target.value || null, {
            onError: (err) => toast({ tone: "danger", title: "Layout not saved", description: errorMessage(err) }),
          })
        }
      >
        <option value="">{defaultName} (default)</option>
        {presets
          .filter((p) => p.key !== default_preset)
          .map((p) => (
            <option key={p.key} value={p.key}>
              {p.name}
            </option>
          ))}
      </Select>
    </label>
  );
}
