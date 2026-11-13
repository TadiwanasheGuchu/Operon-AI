import { Suspense } from "react";

import { OperonMark } from "@/components/brand/operon-mark";
import { WorkspaceGate } from "@/components/layout/workspace-gate";

// The shell reads the URL (navigation, redirects), so it renders at request time; the
// Suspense boundary lets dynamic routes like /integrations/[id] prerender their fallback.
export default function WorkspaceLayout({ children }: { children: React.ReactNode }) {
  return (
    <Suspense
      fallback={
        <div role="status" aria-label="Loading your workspace" className="flex min-h-dvh items-center justify-center bg-canvas">
          <OperonMark className="size-8 animate-pulse text-ocean motion-reduce:animate-none" accent="var(--color-sky)" />
        </div>
      }
    >
      <WorkspaceGate>{children}</WorkspaceGate>
    </Suspense>
  );
}
