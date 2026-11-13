import { OperonMark, OperonWordmark } from "@/components/brand/operon-mark";

export default function AuthLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="grid min-h-dvh bg-canvas lg:grid-cols-[minmax(0,5fr)_minmax(0,7fr)]">
      <aside className="on-nav relative hidden flex-col justify-between overflow-hidden bg-brand p-10 text-ink-brand-muted lg:flex">
        <OperonWordmark className="text-white" />
        <div className="max-w-md">
          <p className="font-display text-[34px] leading-[1.15] text-white">
            Understand your operations. Act with confidence.
          </p>
          <p className="mt-4 text-sm leading-6 text-ink-brand-muted">
            Operon connects operational data, identifies the issues that matter and helps teams
            coordinate the next action, with control at every step.
          </p>
        </div>
        <p className="text-xs text-ink-brand-muted">Every consequential action needs a person&apos;s approval.</p>
        <OperonMark
          aria-hidden
          className="pointer-events-none absolute -right-24 -bottom-24 size-96 text-brand-soft"
          accent="var(--color-sky)"
        />
      </aside>
      <main className="flex flex-col px-4 py-8 sm:px-8">
        <div className="lg:hidden">
          <OperonWordmark className="text-ink" />
        </div>
        <div className="flex flex-1 items-center justify-center py-10">
          <div className="w-full max-w-[400px]">{children}</div>
        </div>
      </main>
    </div>
  );
}
