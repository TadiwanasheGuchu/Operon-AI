import Link from "next/link";

import { OperonMark } from "@/components/brand/operon-mark";
import { Button } from "@/components/ui/button";

export default function NotFound() {
  return (
    <main className="flex min-h-dvh flex-col items-center justify-center gap-4 px-4 text-center">
      <OperonMark className="size-10 text-ocean" accent="var(--color-sky)" />
      <h1 className="font-display text-3xl text-ink">This page doesn&apos;t exist</h1>
      <p className="max-w-sm text-sm text-ink-muted">
        The address may be mistyped, or the module isn&apos;t available in this workspace yet.
      </p>
      <Button asChild>
        <Link href="/overview">Go to overview</Link>
      </Button>
    </main>
  );
}
