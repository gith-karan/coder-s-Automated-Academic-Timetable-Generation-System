import { createContext, useContext, useState, type ReactNode } from "react";
import * as Dialog from "@radix-ui/react-dialog";
import * as Tooltip from "@radix-ui/react-tooltip";
import * as Menu from "@radix-ui/react-dropdown-menu";
import { Info, X } from "lucide-react";
import { cn } from "@/lib/utils";

/* ------------------------------------------------------------------ tooltip */
export const TooltipsEnabled = createContext(true);

export function Tip({ label, children, side = "top" }: { label: ReactNode; children: ReactNode; side?: "top" | "bottom" | "left" | "right" }) {
  const enabled = useContext(TooltipsEnabled);
  if (!enabled || !label) return <>{children}</>;
  return (
    <Tooltip.Root delayDuration={250}>
      <Tooltip.Trigger asChild>{children}</Tooltip.Trigger>
      <Tooltip.Portal>
        <Tooltip.Content
          side={side}
          sideOffset={6}
          className="z-[60] max-w-xs rounded-md bg-[#111827] px-2.5 py-1.5 text-xs text-white shadow-lg animate-fade-in"
        >
          {label}
          <Tooltip.Arrow className="fill-[#111827]" />
        </Tooltip.Content>
      </Tooltip.Portal>
    </Tooltip.Root>
  );
}

/* ------------------------------------------------------------------ modal dialog */
export function Modal({
  open, onOpenChange, title, description, children, footer, size = "md",
}: {
  open: boolean; onOpenChange: (o: boolean) => void; title: ReactNode; description?: ReactNode;
  children: ReactNode; footer?: ReactNode; size?: "sm" | "md" | "lg";
}) {
  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-50 bg-black/40 backdrop-blur-[2px] animate-fade-in" />
        <Dialog.Content
          className={cn(
            "fixed left-1/2 top-1/2 z-50 w-[calc(100vw-2rem)] -translate-x-1/2 -translate-y-1/2 rounded-2xl",
            "border border-line bg-surface shadow-2xl animate-fade-in max-h-[90vh] flex flex-col",
            size === "sm" ? "max-w-md" : size === "lg" ? "max-w-3xl" : "max-w-xl",
          )}
        >
          <div className="flex items-start justify-between gap-4 border-b border-line px-6 py-4">
            <div>
              <Dialog.Title className="text-base font-semibold">{title}</Dialog.Title>
              {description && <Dialog.Description className="mt-0.5 text-sm text-muted">{description}</Dialog.Description>}
            </div>
            <Dialog.Close className="rounded-md p-1 text-muted hover:bg-line/60 hover:text-ink" aria-label="Close">
              <X className="size-4" />
            </Dialog.Close>
          </div>
          <div className="overflow-y-auto px-6 py-5 scrollbar-thin">{children}</div>
          {footer && <div className="flex justify-end gap-2 border-t border-line px-6 py-3">{footer}</div>}
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}

/* ------------------------------------------------------------------ side drawer (keeps list context) */
export function Drawer({
  open, onOpenChange, title, description, children, footer, width = "max-w-xl",
}: {
  open: boolean; onOpenChange: (o: boolean) => void; title: ReactNode; description?: ReactNode;
  children: ReactNode; footer?: ReactNode; width?: string;
}) {
  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-50 bg-black/30 animate-fade-in" />
        <Dialog.Content
          className={cn(
            "fixed right-0 top-0 z-50 flex h-full w-full flex-col border-l border-line bg-surface shadow-2xl",
            "animate-fade-in",
            width,
          )}
        >
          <div className="flex items-start justify-between gap-4 border-b border-line px-6 py-4">
            <div>
              <Dialog.Title className="text-base font-semibold">{title}</Dialog.Title>
              {description && <Dialog.Description className="mt-0.5 text-sm text-muted">{description}</Dialog.Description>}
            </div>
            <Dialog.Close className="rounded-md p-1 text-muted hover:bg-line/60 hover:text-ink" aria-label="Close">
              <X className="size-4" />
            </Dialog.Close>
          </div>
          <div className="flex-1 overflow-y-auto px-6 py-5 scrollbar-thin">{children}</div>
          {footer && <div className="flex justify-end gap-2 border-t border-line px-6 py-3">{footer}</div>}
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}

/* ------------------------------------------------------------------ dropdown menu */
export const MenuRoot = Menu.Root;
export const MenuTrigger = Menu.Trigger;

export function MenuContent({ children, align = "end" }: { children: ReactNode; align?: "start" | "end" }) {
  return (
    <Menu.Portal>
      <Menu.Content
        align={align}
        sideOffset={6}
        className="z-50 min-w-48 rounded-xl border border-line bg-surface p-1 shadow-xl animate-fade-in"
      >
        {children}
      </Menu.Content>
    </Menu.Portal>
  );
}

export function MenuItem({ children, onSelect, danger, icon }: { children: ReactNode; onSelect?: () => void; danger?: boolean; icon?: ReactNode }) {
  return (
    <Menu.Item
      onSelect={onSelect}
      className={cn(
        "flex cursor-pointer select-none items-center gap-2 rounded-lg px-3 py-2 text-sm outline-none",
        "data-[highlighted]:bg-line/60",
        danger ? "text-bad" : "text-ink",
      )}
    >
      {icon}
      {children}
    </Menu.Item>
  );
}

export const MenuSeparator = () => <Menu.Separator className="my-1 h-px bg-line" />;
export const TooltipProvider = Tooltip.Provider;

/* ------------------------------------------------------------------ help icon (ⓘ) */
/** Small info icon that reveals an explanation on hover, focus or tap. Always available, even when
 *  button tooltips are switched off, because it is explicit help the user asked for. */
export function HelpTip({ children, label = "More information", side = "top" }: {
  children: ReactNode; label?: string; side?: "top" | "bottom" | "left" | "right";
}) {
  const [open, setOpen] = useState(false);
  return (
    <Tooltip.Root delayDuration={100} open={open} onOpenChange={setOpen}>
      <Tooltip.Trigger asChild>
        <button type="button" aria-label={label} onClick={(e) => { e.preventDefault(); setOpen((o) => !o); }}
          className="inline-grid size-5 shrink-0 place-items-center rounded-full align-middle text-muted transition-colors hover:text-brand focus-visible:outline-2 focus-visible:outline-brand">
          <Info className="size-4" />
        </button>
      </Tooltip.Trigger>
      <Tooltip.Portal>
        <Tooltip.Content side={side} sideOffset={6} collisionPadding={12}
          className="z-[60] max-w-sm rounded-lg bg-[#111827] px-3 py-2 text-xs leading-relaxed text-white shadow-lg animate-fade-in">
          {children}
          <Tooltip.Arrow className="fill-[#111827]" />
        </Tooltip.Content>
      </Tooltip.Portal>
    </Tooltip.Root>
  );
}
