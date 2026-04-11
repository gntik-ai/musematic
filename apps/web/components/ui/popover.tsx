import * as React from "react";
import { cn } from "@/lib/utils";

interface PopoverContextValue {
  open: boolean;
  setOpen: (open: boolean) => void;
}

const PopoverContext = React.createContext<PopoverContextValue | null>(null);

function usePopoverContext(): PopoverContextValue {
  const context = React.useContext(PopoverContext);
  if (!context) {
    throw new Error("Popover components must be wrapped in Popover");
  }
  return context;
}

export function Popover({
  children,
  open: openProp,
  onOpenChange,
}: React.PropsWithChildren<{ open?: boolean; onOpenChange?: (open: boolean) => void }>) {
  const [internalOpen, setInternalOpen] = React.useState(false);
  const open = openProp ?? internalOpen;
  const setOpen = (nextOpen: boolean) => {
    if (openProp === undefined) {
      setInternalOpen(nextOpen);
    }
    onOpenChange?.(nextOpen);
  };

  return <PopoverContext.Provider value={{ open, setOpen }}>{children}</PopoverContext.Provider>;
}

export function PopoverTrigger({
  asChild,
  children,
}: React.PropsWithChildren<{ asChild?: boolean }>) {
  const { open, setOpen } = usePopoverContext();

  if (asChild && React.isValidElement(children)) {
    return React.cloneElement(children as React.ReactElement<Record<string, unknown>>, {
      onClick: () => setOpen(!open),
    });
  }

  return (
    <button type="button" onClick={() => setOpen(!open)}>
      {children}
    </button>
  );
}

export function PopoverContent({
  className,
  children,
}: React.PropsWithChildren<{ className?: string }>) {
  const { open } = usePopoverContext();
  if (!open) {
    return null;
  }

  return (
    <div className={cn("absolute z-50 mt-2 rounded-md border border-border bg-popover p-3 shadow-lg", className)}>
      {children}
    </div>
  );
}
