"use client";

import { CircleAlert, CircleCheck, FileSearch, MessageSquareText, Plus, SendHorizontal } from "lucide-react";
import Link from "next/link";
import { useEffect, useRef, useState } from "react";

import { InlineAlert } from "@/components/feedback/inline-alert";
import { Button } from "@/components/ui/button";
import { Dialog, DialogDescription, DialogTitle, DrawerContent } from "@/components/ui/dialog";
import { Select } from "@/components/ui/form";
import { Skeleton } from "@/components/ui/skeleton";
import { Tooltip } from "@/components/ui/tooltip";
import {
  type Message,
  useAsk,
  useAssistantStatus,
  useConversation,
  useConversations,
} from "@/features/agents/api";
import { useWorkspace } from "@/features/workspace/workspace-context";
import { errorMessage } from "@/lib/api/client";
import { cn } from "@/lib/cn";

const SUGGESTIONS = [
  "What's most urgent today?",
  "Which purchase orders are late?",
  "What's waiting for approval?",
];

/** Header button that opens the assistant. Hidden for people without assistant.use. */
export function AssistantLauncher() {
  const { workspace } = useWorkspace();
  const [open, setOpen] = useState(false);
  if (!workspace.can("assistant.use")) return null;
  return (
    <>
      <Tooltip content="Ask about your operations">
        <Button variant="secondary" size="sm" onClick={() => setOpen(true)} aria-haspopup="dialog" aria-label="Ask about your operations">
          <MessageSquareText aria-hidden /> <span className="hidden sm:inline">Ask</span>
        </Button>
      </Tooltip>
      <Dialog open={open} onOpenChange={setOpen}>
        <DrawerContent side="right" className="w-[min(480px,calc(100vw-24px))] border-l border-line bg-raised">
          <AssistantPanel open={open} onNavigate={() => setOpen(false)} />
        </DrawerContent>
      </Dialog>
    </>
  );
}

function AssistantPanel({ open, onNavigate }: { open: boolean; onNavigate: () => void }) {
  const status = useAssistantStatus(open);
  const conversations = useConversations(open);
  const [conversationId, setConversationId] = useState<string | null>(null);
  const conversation = useConversation(conversationId);
  const ask = useAsk();
  const [question, setQuestion] = useState("");
  const [pending, setPending] = useState<string | null>(null);
  const end = useRef<HTMLDivElement>(null);
  const messages = conversation.data?.messages ?? [];

  useEffect(() => {
    end.current?.scrollIntoView({ block: "end" });
  }, [messages.length, pending]);

  const send = (text: string) => {
    const q = text.trim();
    if (q.length < 2 || ask.isPending) return;
    setPending(q);
    setQuestion("");
    ask.mutate(
      { question: q, conversation_id: conversationId },
      {
        onSuccess: (r) => setConversationId(r.conversation_id),
        onError: () => setQuestion(q),
        onSettled: () => setPending(null),
      },
    );
  };

  return (
    <div className="flex h-full flex-col">
      <div className="border-b border-line px-5 py-4 pr-12">
        <DialogTitle className="text-base font-semibold text-ink">Ask about your operations</DialogTitle>
        <DialogDescription className="mt-0.5 text-xs text-ink-muted">
          Answers come from records you can already see, with references. The assistant can&apos;t change anything.
        </DialogDescription>
        <div className="mt-3 flex items-center gap-2">
          <label htmlFor="conversation-select" className="sr-only">
            Conversation
          </label>
          <Select
            id="conversation-select"
            className="h-8 flex-1 text-[13px]"
            value={conversationId ?? ""}
            onChange={(e) => setConversationId(e.target.value || null)}
          >
            <option value="">New conversation</option>
            {conversations.data?.map((c) => (
              <option key={c.id} value={c.id}>
                {c.title}
              </option>
            ))}
          </Select>
          <Button variant="tertiary" size="sm" onClick={() => setConversationId(null)} disabled={!conversationId}>
            <Plus aria-hidden /> New
          </Button>
        </div>
      </div>

      <div className="flex-1 space-y-4 overflow-y-auto px-5 py-4" aria-live="polite">
        {status.isPending ? (
          <Skeleton className="h-16 w-full" />
        ) : status.data && !status.data.available ? (
          <InlineAlert tone="info" title="The assistant isn't available">
            {status.data.reason}
          </InlineAlert>
        ) : messages.length === 0 && !pending ? (
          <div>
            <p className="text-sm text-ink-secondary">Try asking:</p>
            <ul className="mt-2 space-y-1.5">
              {SUGGESTIONS.map((s) => (
                <li key={s}>
                  <button
                    type="button"
                    onClick={() => send(s)}
                    className="w-full rounded-control border border-line px-3 py-2 text-left text-[13px] text-ink hover:bg-sunken"
                  >
                    {s}
                  </button>
                </li>
              ))}
            </ul>
          </div>
        ) : null}
        {messages.map((m) => (
          <MessageView key={m.id} message={m} onNavigate={onNavigate} />
        ))}
        {pending ? (
          <>
            <MessageView
              message={{ id: "pending", role: "user", content: pending, citations: [], checked: true, problems: [], execution_id: null, created_at: "" }}
              onNavigate={onNavigate}
            />
            <div role="status" className="space-y-2">
              <p className="text-xs text-ink-muted">Looking up records…</p>
              <Skeleton className="h-4 w-3/4" />
              <Skeleton className="h-4 w-1/2" />
            </div>
          </>
        ) : null}
        {ask.isError ? (
          <InlineAlert tone="danger" title="No answer">
            {errorMessage(ask.error)}
          </InlineAlert>
        ) : null}
        <div ref={end} />
      </div>

      <form
        className="border-t border-line p-4"
        onSubmit={(e) => {
          e.preventDefault();
          send(question);
        }}
      >
        <label htmlFor="assistant-question" className="sr-only">
          Your question
        </label>
        <div className="flex items-end gap-2">
          <textarea
            id="assistant-question"
            rows={2}
            maxLength={2000}
            value={question}
            disabled={status.data?.available === false}
            placeholder="Ask about insights, stock, orders, incidents…"
            onChange={(e) => setQuestion(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                send(question);
              }
            }}
            className="min-h-10 flex-1 resize-none rounded-control border border-line-control bg-raised px-3 py-2 text-sm text-ink placeholder:text-ink-muted hover:border-ink-secondary focus-visible:border-primary disabled:bg-sunken"
          />
          <Button type="submit" size="icon" aria-label="Send" loading={ask.isPending} disabled={question.trim().length < 2 || status.data?.available === false}>
            {ask.isPending ? null : <SendHorizontal aria-hidden />}
          </Button>
        </div>
      </form>
    </div>
  );
}

/** Renders references like [INS-0001] as links when the answer cited a record it looked up. */
function withCitations(text: string, message: Message, onNavigate: () => void) {
  const byRef = new Map(message.citations.map((c) => [c.ref, c]));
  const parts = text.split(/(\[[^\]]{1,62}\])/g);
  return parts.map((part, i) => {
    const ref = part.startsWith("[") ? part.slice(1, -1) : null;
    const c = ref ? byRef.get(ref) : undefined;
    if (!c) return <span key={i}>{part}</span>;
    return c.href ? (
      <Link key={i} href={c.href} onClick={onNavigate} className="font-mono text-[12px] font-medium text-primary underline underline-offset-2" title={c.label}>
        {c.ref}
      </Link>
    ) : (
      <span key={i} className="font-mono text-[12px] font-medium text-ink" title={c.label}>
        {c.ref}
      </span>
    );
  });
}

function MessageView({ message: m, onNavigate }: { message: Message; onNavigate: () => void }) {
  if (m.role === "user") {
    return (
      <div className="ml-8 rounded-[10px] bg-selected px-3.5 py-2.5 text-sm text-ink">
        <span className="sr-only">You asked: </span>
        {m.content}
      </div>
    );
  }
  return (
    <article className="space-y-2">
      <p className="text-sm leading-6 whitespace-pre-wrap text-ink">{withCitations(m.content, m, onNavigate)}</p>
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs">
        {m.checked ? (
          <span className="inline-flex items-center gap-1 text-success">
            <CircleCheck className="size-3.5" aria-hidden /> Checked against the records it used
          </span>
        ) : (
          <span className={cn("inline-flex items-start gap-1 text-warning")}>
            <CircleAlert className="mt-px size-3.5 shrink-0" aria-hidden />
            <span>Not fully verified: {m.problems.join(" ")}</span>
          </span>
        )}
        {m.execution_id ? (
          <Link href={`/agents/runs/${m.execution_id}`} onClick={onNavigate} className="inline-flex items-center gap-1 text-ink-muted underline underline-offset-2 hover:text-ink">
            <FileSearch className="size-3.5" aria-hidden /> How this was answered
          </Link>
        ) : null}
      </div>
    </article>
  );
}
