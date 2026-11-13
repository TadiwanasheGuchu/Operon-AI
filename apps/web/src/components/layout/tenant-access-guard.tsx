"use client";

import { ShieldAlert } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";

import { Button } from "@/components/ui/button";
import { useCurrentOrganisation } from "@/features/session/use-session";
import { ApiRequestError } from "@/lib/api/client";

/**
 * When the organisation's MFA policy blocks the user, organisation pages explain why and point to
 * the fix. Account pages stay reachable so the user can actually enable MFA.
 */
export function TenantAccessGuard({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const current = useCurrentOrganisation();
  const blocked =
    !pathname.startsWith("/account") &&
    current.error instanceof ApiRequestError &&
    current.error.code === "mfa_required";
  if (!blocked) return children;
  return (
    <div role="alert" className="mx-auto flex max-w-lg flex-col items-center px-4 py-20 text-center">
      <span className="inline-flex size-12 items-center justify-center rounded-full bg-warning-bg text-warning">
        <ShieldAlert className="size-6" aria-hidden />
      </span>
      <h1 className="mt-4 font-display text-[28px] leading-9 text-ink">Two-factor authentication required</h1>
      <p className="mt-2 text-sm text-ink-secondary">
        This organisation requires every member to use two-factor authentication. Turn it on for your
        account to continue. It takes about a minute with an authenticator app.
      </p>
      <Button asChild className="mt-6">
        <Link href="/account/security">Set up two-factor authentication</Link>
      </Button>
    </div>
  );
}
