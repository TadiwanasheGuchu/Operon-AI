export function AuthHeading({ title, description }: { title: string; description?: React.ReactNode }) {
  return (
    <div className="mb-7">
      <h1 className="font-display text-[30px] leading-9 font-medium tracking-[-0.01em] text-ink">{title}</h1>
      {description ? <p className="mt-2 text-sm text-ink-secondary">{description}</p> : null}
    </div>
  );
}
