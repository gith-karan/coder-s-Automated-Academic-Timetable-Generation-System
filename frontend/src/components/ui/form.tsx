import { forwardRef, useId, type InputHTMLAttributes, type ReactNode, type SelectHTMLAttributes, type TextareaHTMLAttributes } from "react";
import * as SwitchPrimitive from "@radix-ui/react-switch";
import { cn } from "@/lib/utils";
import { HelpTip } from "./overlay";

const control =
  "w-full rounded-[10px] border border-line bg-surface px-3 text-sm text-ink placeholder:text-muted/70 " +
  "transition-colors focus:border-brand focus:outline-none focus:ring-2 focus:ring-brand/20 disabled:opacity-60";

export function Field({ label, error, hint, help, children, htmlFor, required, className }: {
  label?: ReactNode; error?: string; hint?: ReactNode; help?: ReactNode; children: ReactNode; htmlFor?: string;
  required?: boolean; className?: string;
}) {
  return (
    <div className={cn("space-y-1.5", className)}>
      {label && (
        <div className="flex items-center gap-1">
          <label htmlFor={htmlFor} className="block text-xs font-medium text-muted">
            {label} {required && <span className="text-bad">*</span>}
          </label>
          {help && <HelpTip>{help}</HelpTip>}
        </div>
      )}
      {children}
      {error ? <p className="text-xs text-bad" role="alert">{error}</p> : hint ? <p className="text-xs text-muted">{hint}</p> : null}
    </div>
  );
}

export interface InputProps extends InputHTMLAttributes<HTMLInputElement> {
  icon?: ReactNode;
  invalid?: boolean;
  trailing?: ReactNode;
}

export const Input = forwardRef<HTMLInputElement, InputProps>(function Input({ icon, invalid, trailing, className, ...rest }, ref) {
  return (
    <div className="relative">
      {icon && <span className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-muted [&>svg]:size-4">{icon}</span>}
      <input
        ref={ref}
        aria-invalid={invalid || undefined}
        className={cn(control, "h-10", icon && "pl-9", trailing && "pr-10", invalid && "border-bad focus:border-bad focus:ring-bad/20", className)}
        {...rest}
      />
      {trailing && <span className="absolute right-2 top-1/2 -translate-y-1/2">{trailing}</span>}
    </div>
  );
});

export const Select = forwardRef<HTMLSelectElement, SelectHTMLAttributes<HTMLSelectElement> & { invalid?: boolean }>(
  function Select({ className, invalid, children, ...rest }, ref) {
    return (
      <select ref={ref} className={cn(control, "h-10 pr-8", invalid && "border-bad", className)} {...rest}>
        {children}
      </select>
    );
  },
);

export const Textarea = forwardRef<HTMLTextAreaElement, TextareaHTMLAttributes<HTMLTextAreaElement>>(function Textarea(
  { className, ...rest }, ref,
) {
  return <textarea ref={ref} className={cn(control, "min-h-20 py-2", className)} {...rest} />;
});

export function Switch({ checked, onCheckedChange, label, description, disabled }: {
  checked: boolean; onCheckedChange: (v: boolean) => void; label?: ReactNode; description?: ReactNode; disabled?: boolean;
}) {
  const id = useId();
  return (
    <div className="flex items-center justify-between gap-4">
      {(label || description) && (
        <label htmlFor={id} className="cursor-pointer">
          {label && <span className="block text-sm font-medium">{label}</span>}
          {description && <span className="block text-xs text-muted">{description}</span>}
        </label>
      )}
      <SwitchPrimitive.Root
        id={id}
        checked={checked}
        disabled={disabled}
        onCheckedChange={onCheckedChange}
        className="relative h-6 w-11 shrink-0 rounded-full bg-line transition-colors data-[state=checked]:bg-brand disabled:opacity-50 focus-visible:outline-2 focus-visible:outline-brand"
      >
        <SwitchPrimitive.Thumb className="block size-5 translate-x-0.5 rounded-full bg-white shadow transition-transform data-[state=checked]:translate-x-[22px]" />
      </SwitchPrimitive.Root>
    </div>
  );
}

/** Segmented control (e.g. Light / Dark / System, Hard / Soft / Off). */
export function Segmented<T extends string>({ value, onChange, options, size = "md" }: {
  value: T; onChange: (v: T) => void; options: { value: T; label: ReactNode; icon?: ReactNode; disabled?: boolean }[]; size?: "sm" | "md";
}) {
  return (
    <div role="radiogroup" className="inline-flex rounded-[10px] border border-line bg-surface-2 p-0.5">
      {options.map((o) => (
        <button
          key={o.value}
          type="button"
          role="radio"
          aria-checked={value === o.value}
          disabled={o.disabled}
          onClick={() => onChange(o.value)}
          className={cn(
            "inline-flex items-center gap-1.5 rounded-[8px] font-medium transition-colors disabled:opacity-40",
            size === "sm" ? "px-2.5 py-1 text-xs" : "px-3.5 py-1.5 text-sm",
            value === o.value ? "bg-surface text-brand shadow-sm ring-1 ring-brand/30" : "text-muted hover:text-ink",
          )}
        >
          {o.icon}
          {o.label}
        </button>
      ))}
    </div>
  );
}
