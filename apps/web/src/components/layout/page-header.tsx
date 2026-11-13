export function PageHeader({
  title,
  description,
  actions,
}: {
  title: string;
  description?: React.ReactNode;
  actions?: React.ReactNode;
}) {
  return (
    <div className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
      <div className="min-w-0">
        <h1 className="font-display text-[30px] leading-9 font-medium tracking-[-0.01em] text-ink">{title}</h1>
        {description ? <p className="mt-1.5 max-w-2xl text-sm text-ink-secondary">{description}</p> : null}
      </div>
      {actions ? <div className="flex shrink-0 flex-wrap items-center gap-2">{actions}</div> : null}
    </div>
  );
}

export function PageContainer({ children, narrow }: { children: React.ReactNode; narrow?: boolean }) {
  return (
    <div className={`mx-auto px-4 pt-6 pb-12 md:px-6 lg:px-9 lg:pt-8 ${narrow ? "max-w-[880px]" : "max-w-[1200px]"}`}>
      {children}
    </div>
  );
}
