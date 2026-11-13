import { CircleX, Inbox, Lock, type LucideIcon } from "lucide-react";

import { Button } from "@/components/ui/button";
import { cn } from "@/lib/cn";

function StateFrame({
  icon: Icon,
  iconClass,
  title,
  description,
  action,
  compact,
  role,
  className,
}: {
  icon: LucideIcon;
  iconClass: string;
  title: string;
  description?: React.ReactNode;
  action?: React.ReactNode;
  compact?: boolean;
  role?: "status" | "alert";
  className?: string;
}) {
  return (
    <div
      role={role}
      className={cn(
        "flex flex-col items-center text-center",
        compact ? "gap-2 px-4 py-6" : "gap-3 px-6 py-12",
        className,
      )}
    >
      <span className={cn("inline-flex size-10 items-center justify-center rounded-full", iconClass)}>
        <Icon className="size-5" aria-hidden />
      </span>
      <div className="max-w-sm">
        <p className="text-sm font-semibold text-ink">{title}</p>
        {description ? <p className="mt-1 text-[13px] text-ink-muted">{description}</p> : null}
      </div>
      {action}
    </div>
  );
}

export function EmptyState(props: {
  title: string;
  description?: React.ReactNode;
  action?: React.ReactNode;
  icon?: LucideIcon;
  compact?: boolean;
}) {
  return <StateFrame icon={props.icon ?? Inbox} iconClass="bg-sunken text-ink-muted" role="status" {...props} />;
}

export function ErrorState({
  title = "This information couldn't be loaded",
  description,
  onRetry,
  requestId,
  compact,
}: {
  title?: string;
  description?: React.ReactNode;
  onRetry?: () => void;
  requestId?: string | null;
  compact?: boolean;
}) {
  return (
    <StateFrame
      icon={CircleX}
      iconClass="bg-danger-bg text-danger"
      role="alert"
      title={title}
      compact={compact}
      description={
        <>
          {description ?? "Try again. If the problem continues, contact your administrator."}
          {requestId ? (
            <span className="mt-1 block font-mono text-[11px]">Request ID {requestId}</span>
          ) : null}
        </>
      }
      action={
        onRetry ? (
          <Button variant="secondary" size="sm" onClick={onRetry}>
            Try again
          </Button>
        ) : undefined
      }
    />
  );
}

export function PermissionDenied({
  permission,
  description,
  compact,
}: {
  permission: string;
  description?: React.ReactNode;
  compact?: boolean;
}) {
  return (
    <StateFrame
      icon={Lock}
      iconClass="bg-sunken text-ink-secondary"
      role="status"
      title="You don't have access to this information"
      compact={compact}
      description={
        <>
          {description ?? "Ask an organisation administrator to grant access if you need it."}
          <span className="mt-1 block font-mono text-[11px]">Requires {permission}</span>
        </>
      }
    />
  );
}
