import { forwardRef, type ButtonHTMLAttributes, type ReactNode } from "react";
import { Loader2 } from "lucide-react";
import { cn } from "@/lib/utils";
import { Tip } from "./overlay";

type Variant = "primary" | "secondary" | "ghost" | "danger" | "outline";
type Size = "sm" | "md" | "lg";

const variants: Record<Variant, string> = {
  primary: "bg-brand text-brand-fg hover:bg-brand-strong shadow-sm",
  secondary: "bg-surface-2 text-ink border border-line hover:bg-line/60",
  outline: "border border-brand/40 text-brand hover:bg-brand/8 bg-transparent",
  ghost: "text-muted hover:text-ink hover:bg-line/50",
  danger: "bg-bad text-white hover:opacity-90",
};
const sizes: Record<Size, string> = {
  sm: "h-8 px-3 text-xs gap-1.5",
  md: "h-9 px-4 text-sm gap-2",
  lg: "h-11 px-5 text-sm gap-2",
};

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
  size?: Size;
  loading?: boolean;
  icon?: ReactNode;
}

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(function Button(
  { variant = "primary", size = "md", loading, icon, className, children, disabled, ...rest },
  ref,
) {
  return (
    <button
      ref={ref}
      disabled={disabled || loading}
      className={cn(
        "inline-flex items-center justify-center rounded-[10px] font-medium transition-colors select-none",
        "focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand",
        "disabled:opacity-50 disabled:pointer-events-none whitespace-nowrap",
        variants[variant],
        sizes[size],
        className,
      )}
      {...rest}
    >
      {loading ? <Loader2 className="size-4 animate-spin" /> : icon}
      {children}
    </button>
  );
});

export interface IconButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  label: string; // accessible name + tooltip
  variant?: Variant;
  size?: "sm" | "md";
  loading?: boolean;
  children: ReactNode;
}

/** Icon-only button. Always has an accessible label and a tooltip. */
export const IconButton = forwardRef<HTMLButtonElement, IconButtonProps>(function IconButton(
  { label, variant = "ghost", size = "md", loading, className, children, disabled, ...rest },
  ref,
) {
  return (
    <Tip label={label}>
      <button
        ref={ref}
        aria-label={label}
        disabled={disabled || loading}
        className={cn(
          "inline-flex items-center justify-center rounded-[10px] transition-colors shrink-0",
          "focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand disabled:opacity-40",
          size === "sm" ? "size-8" : "size-9",
          variants[variant],
          variant === "ghost" && "border-0",
          className,
        )}
        {...rest}
      >
        {loading ? <Loader2 className="size-4 animate-spin" /> : children}
      </button>
    </Tip>
  );
});
