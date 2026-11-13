"use client";

import { useState } from "react";

import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogTitle } from "@/components/ui/dialog";
import { Field } from "@/components/ui/form";

/** Asks for a short note before a status change (required for dismissals and resolutions). */
export function ReasonDialog({
  open,
  onOpenChange,
  title,
  description,
  label,
  required,
  confirmLabel,
  onSubmit,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: string;
  description: React.ReactNode;
  label: string;
  required: boolean;
  confirmLabel: string;
  onSubmit: (reason: string) => Promise<unknown>;
}) {
  const [reason, setReason] = useState("");
  const [error, setError] = useState<string | undefined>();
  const [busy, setBusy] = useState(false);
  return (
    <Dialog
      open={open}
      onOpenChange={(o) => {
        if (busy) return;
        if (!o) {
          setReason("");
          setError(undefined);
        }
        onOpenChange(o);
      }}
    >
      <DialogContent className="p-6">
        <DialogTitle className="text-base font-semibold text-ink">{title}</DialogTitle>
        <DialogDescription className="mt-2 text-sm text-ink-secondary">{description}</DialogDescription>
        <form
          className="mt-4 space-y-4"
          onSubmit={async (e) => {
            e.preventDefault();
            if (required && !reason.trim()) {
              setError("Add a short note so others know why.");
              return;
            }
            setBusy(true);
            try {
              await onSubmit(reason.trim());
              setReason("");
              onOpenChange(false);
            } catch {
              // The caller reports the error; keep the dialog open with the text intact.
            } finally {
              setBusy(false);
            }
          }}
        >
          <Field label={label} error={error} hint={required ? undefined : "Optional"}>
            {(p) => (
              <textarea
                {...p}
                rows={3}
                maxLength={500}
                value={reason}
                onChange={(e) => {
                  setReason(e.target.value);
                  setError(undefined);
                }}
                className="w-full rounded-control border border-line-control bg-raised px-3 py-2 text-sm text-ink placeholder:text-ink-muted hover:border-ink-secondary focus-visible:border-primary aria-[invalid=true]:border-danger"
              />
            )}
          </Field>
          <div className="flex justify-end gap-2">
            <Button type="button" variant="secondary" onClick={() => onOpenChange(false)} disabled={busy}>
              Cancel
            </Button>
            <Button type="submit" loading={busy}>
              {confirmLabel}
            </Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  );
}
