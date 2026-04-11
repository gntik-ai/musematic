import * as React from "react";
import { cn } from "@/lib/utils";

export function Command({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return <div className={cn("flex h-full w-full flex-col overflow-hidden rounded-md bg-popover", className)} {...props} />;
}

export function CommandDialog({
  open,
  onOpenChange,
  children,
}: React.PropsWithChildren<{ open: boolean; onOpenChange: (open: boolean) => void }>) {
  if (!open) {
    return null;
  }

  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center bg-black/50 px-4 pt-24" onClick={() => onOpenChange(false)}>
      <div
        className="w-full max-w-2xl rounded-2xl border border-border bg-popover p-4 shadow-2xl"
        onClick={(event) => event.stopPropagation()}
      >
        {children}
      </div>
    </div>
  );
}

export function CommandInput(props: React.InputHTMLAttributes<HTMLInputElement>) {
  return (
    <input
      className="flex h-12 w-full rounded-lg border border-input bg-background px-4 text-sm outline-none placeholder:text-muted-foreground"
      autoFocus
      {...props}
    />
  );
}

export function CommandList({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return <div className={cn("mt-3 max-h-[24rem] overflow-y-auto", className)} {...props} />;
}

export function CommandEmpty({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return <div className={cn("py-8 text-center text-sm text-muted-foreground", className)} {...props} />;
}

export function CommandGroup({
  heading,
  children,
}: React.PropsWithChildren<{ heading?: string }>) {
  return (
    <div className="py-2">
      {heading ? <p className="px-2 pb-2 text-xs font-semibold uppercase tracking-[0.2em] text-muted-foreground">{heading}</p> : null}
      <div className="space-y-1">{children}</div>
    </div>
  );
}

export function CommandItem({
  className,
  children,
  ...props
}: React.ButtonHTMLAttributes<HTMLButtonElement>) {
  return (
    <button
      type="button"
      className={cn(
        "flex w-full items-center justify-between rounded-lg px-3 py-2 text-left text-sm transition-colors hover:bg-accent hover:text-accent-foreground",
        className,
      )}
      {...props}
    >
      {children}
    </button>
  );
}

export function CommandSeparator() {
  return <div className="my-2 h-px bg-border" />;
}
