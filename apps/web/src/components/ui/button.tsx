import { cva, type VariantProps } from "class-variance-authority";
import { LoaderCircle } from "lucide-react";
import { Slot } from "radix-ui";
import type { ComponentProps } from "react";

import { cn } from "@/lib/cn";

export const buttonVariants = cva(
  [
    "inline-flex shrink-0 items-center justify-center gap-2 whitespace-nowrap font-medium",
    "rounded-control transition-colors transition-standard select-none",
    "disabled:cursor-not-allowed aria-disabled:cursor-not-allowed",
    "[&_svg]:size-4 [&_svg]:shrink-0",
  ],
  {
    variants: {
      variant: {
        primary:
          "bg-primary text-ink-inverse hover:bg-primary-hover active:bg-harbour disabled:bg-shallows disabled:text-ink-secondary",
        secondary:
          "border border-line bg-raised text-ink hover:border-line-control hover:bg-sunken active:bg-selected disabled:text-ink-muted disabled:hover:bg-raised",
        tertiary:
          "text-ink-secondary hover:bg-sunken hover:text-ink active:bg-selected disabled:text-ink-muted disabled:hover:bg-transparent",
        destructive:
          "bg-danger text-ink-inverse hover:bg-danger-hover active:bg-danger-hover disabled:opacity-50",
        quiet:
          "text-ink-secondary hover:bg-sunken hover:text-ink active:bg-selected disabled:text-ink-muted",
      },
      size: {
        sm: "h-8 px-3 text-[13px]",
        md: "h-9 px-3.5 text-sm",
        icon: "size-9",
        "icon-sm": "size-8",
      },
    },
    defaultVariants: { variant: "primary", size: "md" },
  },
);

type ButtonProps = ComponentProps<"button"> &
  VariantProps<typeof buttonVariants> & {
    asChild?: boolean;
    loading?: boolean;
  };

export function Button({
  className,
  variant,
  size,
  asChild = false,
  loading = false,
  disabled,
  children,
  ...props
}: ButtonProps) {
  const Comp = asChild ? Slot.Root : "button";
  return (
    <Comp
      className={cn(buttonVariants({ variant, size }), className)}
      disabled={asChild ? undefined : disabled || loading}
      aria-busy={loading || undefined}
      {...props}
    >
      {asChild ? (
        children
      ) : (
        <>
          {loading ? <LoaderCircle className="animate-spin" aria-hidden /> : null}
          {children}
        </>
      )}
    </Comp>
  );
}
