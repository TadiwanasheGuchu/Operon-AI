"use client";

import { useState } from "react";

import { useToast } from "@/components/feedback/toast";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogTitle } from "@/components/ui/dialog";
import { Field } from "@/components/ui/form";
import { type ExecutionDetail, type ExecutionSummary, type Approval, useWorkflowMutation } from "@/features/workflows/api";
import { api, errorMessage } from "@/lib/api/client";

/** Approve (comment optional) or reject (reason required) one approval stage. */
export function DecisionDialog({
  execution,
  approval,
  decision,
  onOpenChange,
}: {
  execution: ExecutionSummary;
  approval: Approval;
  decision: "approve" | "reject" | null;
  onOpenChange: (open: boolean) => void;
}) {
  const toast = useToast();
  const [comment, setComment] = useState("");
  const [error, setError] = useState<string | undefined>();
  const decide = useWorkflowMutation((v: { decision: "approve" | "reject"; comment: string }) =>
    api.post<ExecutionDetail>(`/approvals/${approval.id}/decision`, v),
  );
  const approving = decision === "approve";
  return (
    <Dialog
      open={decision !== null}
      onOpenChange={(o) => {
        if (decide.isPending) return;
        if (!o) {
          setComment("");
          setError(undefined);
        }
        onOpenChange(o);
      }}
    >
      <DialogContent className="p-6">
        <DialogTitle className="text-base font-semibold text-ink">
          {approving ? "Approve" : "Reject"} {execution.reference}
        </DialogTitle>
        <DialogDescription className="mt-2 text-sm text-ink-secondary">
          {execution.title}
          {execution.value_display ? ` · ${execution.value_display}` : ""}
          {execution.supplier_name ? ` from ${execution.supplier_name}` : ""}. {approval.name}.
          {approving
            ? " If this is the last stage, the order is sent to the purchasing system straight away."
            : " The request ends and nothing is ordered."}
        </DialogDescription>
        <form
          className="mt-4 space-y-4"
          onSubmit={(e) => {
            e.preventDefault();
            if (!approving && !comment.trim()) {
              setError("Say why, so the requester knows what to change.");
              return;
            }
            decide.mutate(
              { decision: approving ? "approve" : "reject", comment: comment.trim() },
              {
                onSuccess: () => {
                  toast({ tone: "success", title: `${execution.reference} ${approving ? "approved" : "rejected"}` });
                  setComment("");
                  onOpenChange(false);
                },
                onError: (err) => toast({ tone: "danger", title: "Decision not recorded", description: errorMessage(err) }),
              },
            );
          }}
        >
          <Field label={approving ? "Comment" : "Reason"} hint={approving ? "Optional" : undefined} error={error}>
            {(p) => (
              <textarea
                {...p}
                rows={3}
                maxLength={2000}
                value={comment}
                onChange={(e) => {
                  setComment(e.target.value);
                  setError(undefined);
                }}
                className="w-full rounded-control border border-line-control bg-raised px-3 py-2 text-sm text-ink hover:border-ink-secondary focus-visible:border-primary aria-[invalid=true]:border-danger"
              />
            )}
          </Field>
          <div className="flex justify-end gap-2">
            <Button type="button" variant="secondary" onClick={() => onOpenChange(false)} disabled={decide.isPending}>
              Cancel
            </Button>
            <Button type="submit" variant={approving ? "primary" : "destructive"} loading={decide.isPending}>
              {approving ? "Approve" : "Reject"}
            </Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  );
}
