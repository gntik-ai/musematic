import * as React from "react";
import { cn } from "@/lib/utils";

interface DropdownMenuContextValue {
  open: boolean;
  setOpen: (open: boolean) => void;
}

const DropdownMenuContext = React.createContext<DropdownMenuContextValue | null>(null);

function useDropdownMenuContext(): DropdownMenuContextValue {
  const context = React.useContext(DropdownMenuContext);
  if (!context) {
    throw new Error("DropdownMenu components must be wrapped in DropdownMenu");
  }
  return context;
}

export function DropdownMenu({
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

  return (
    <DropdownMenuContext.Provider value={{ open, setOpen }}>
      <div className="relative inline-flex">{children}</div>
    </DropdownMenuContext.Provider>
  );
}

export function DropdownMenuTrigger({
  asChild,
  children,
  ...props
}: React.ButtonHTMLAttributes<HTMLButtonElement> & { asChild?: boolean }) {
  const { open, setOpen } = useDropdownMenuContext();

  if (asChild && React.isValidElement(children)) {
    return React.cloneElement(children as React.ReactElement<Record<string, unknown>>, {
      ...props,
      onClick: () => setOpen(!open),
    });
  }

  return (
    <button {...props} type="button" onClick={() => setOpen(!open)}>
      {children}
    </button>
  );
}

export function DropdownMenuContent({
  align = "start",
  className,
  children,
}: React.PropsWithChildren<{ align?: "start" | "end"; className?: string }>) {
  const { open } = useDropdownMenuContext();
  if (!open) {
    return null;
  }

  return (
    <div
      className={cn(
        "absolute top-full z-50 mt-2 min-w-48 rounded-md border border-border bg-popover p-1 text-popover-foreground shadow-lg",
        align === "end" ? "right-0" : "left-0",
        className,
      )}
    >
      {children}
    </div>
  );
}

export function DropdownMenuLabel({
  className,
  ...props
}: React.HTMLAttributes<HTMLDivElement>) {
  return <div className={cn("px-2 py-1.5 text-sm font-semibold", className)} {...props} />;
}

export function DropdownMenuSeparator({ className }: { className?: string }) {
  return <div className={cn("-mx-1 my-1 h-px bg-border", className)} />;
}

export function DropdownMenuItem({
  className,
  inset,
  ...props
}: React.ButtonHTMLAttributes<HTMLButtonElement> & { inset?: boolean }) {
  const { setOpen } = useDropdownMenuContext();
  return (
    <button
      type="button"
      className={cn(
        "flex w-full items-center gap-2 rounded-sm px-2 py-1.5 text-sm outline-none transition-colors hover:bg-accent hover:text-accent-foreground",
        inset && "pl-8",
        className,
      )}
      onClick={(event) => {
        props.onClick?.(event);
        setOpen(false);
      }}
      {...props}
    />
  );
}
