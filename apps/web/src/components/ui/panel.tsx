import { cn } from "@/lib/cn";

/** Flat bordered surface. The default container for a dashboard section. */
export function Panel({
  className,
  children,
  flat = false,
  ...props
}: React.ComponentProps<"section"> & {
  /** Open section on the page background, divided by a rule: for primary reading content. */
  flat?: boolean;
}) {
  return (
    <section
      data-flat={flat || undefined}
      className={cn(flat ? "flat-section border-t border-line pt-1" : "rounded-panel border border-line bg-raised", className)}
      {...props}
    >
      {children}
    </section>
  );
}

export function PanelHeader({
  title,
  description,
  actions,
  id,
  className,
}: {
  title: string;
  description?: React.ReactNode;
  actions?: React.ReactNode;
  id?: string;
  className?: string;
}) {
  return (
    <header className={cn("flex items-start justify-between gap-4 px-5 pt-4 pb-3", className)}>
      <div className="min-w-0">
        <h2 id={id} className="text-[15px] font-semibold leading-6 text-ink">
          {title}
        </h2>
        {description ? (
          <p className="mt-0.5 text-[13px] leading-5 text-ink-muted">{description}</p>
        ) : null}
      </div>
      {actions ? <div className="flex shrink-0 items-center gap-2">{actions}</div> : null}
    </header>
  );
}

export function PanelBody({ className, ...props }: React.ComponentProps<"div">) {
  return <div className={cn("px-5 pb-5", className)} {...props} />;
}
