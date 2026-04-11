"use client";

import * as React from "react";
import { createPortal } from "react-dom";
import { cn } from "@/lib/utils";

interface DialogContextValue {
  open: boolean;
  setOpen: (open: boolean) => void;
}

type DismissableEvent = {
  defaultPrevented: boolean;
  preventDefault: () => void;
  originalEvent?: Event;
};

const DialogContext = React.createContext<DialogContextValue | null>(null);

function useDialogContext(): DialogContextValue {
  const context = React.useContext(DialogContext);
  if (!context) {
    throw new Error("Dialog components must be wrapped in <Dialog>.");
  }
  return context;
}

function createDismissableEvent(originalEvent?: Event): DismissableEvent {
  let prevented = false;
  return {
    originalEvent,
    get defaultPrevented() {
      return prevented;
    },
    preventDefault() {
      prevented = true;
    },
  };
}

export function Dialog({
  children,
  open,
  onOpenChange,
}: React.PropsWithChildren<{ open: boolean; onOpenChange: (open: boolean) => void }>) {
  return (
    <DialogContext.Provider value={{ open, setOpen: onOpenChange }}>
      {children}
    </DialogContext.Provider>
  );
}

export function DialogTrigger({
  asChild,
  children,
}: React.PropsWithChildren<{ asChild?: boolean }>) {
  const { open, setOpen } = useDialogContext();

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

export function DialogContent({
  children,
  className,
  onEscapeKeyDown,
  onInteractOutside,
  ...props
}: React.HTMLAttributes<HTMLDivElement> & {
  onEscapeKeyDown?: (event: DismissableEvent) => void;
  onInteractOutside?: (event: DismissableEvent) => void;
}) {
  const { open, setOpen } = useDialogContext();
  const [mounted, setMounted] = React.useState(false);

  React.useEffect(() => {
    setMounted(true);
  }, []);

  React.useEffect(() => {
    if (!open) {
      return undefined;
    }

    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key !== "Escape") {
        return;
      }

      const dismissEvent = createDismissableEvent(event);
      onEscapeKeyDown?.(dismissEvent);
      if (!dismissEvent.defaultPrevented) {
        setOpen(false);
      }
    };

    window.addEventListener("keydown", handleKeyDown);
    return () => {
      window.removeEventListener("keydown", handleKeyDown);
    };
  }, [onEscapeKeyDown, open, setOpen]);

  if (!mounted || !open) {
    return null;
  }

  return createPortal(
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4"
      onMouseDown={(event) => {
        if (event.target !== event.currentTarget) {
          return;
        }

        const dismissEvent = createDismissableEvent(event.nativeEvent);
        onInteractOutside?.(dismissEvent);
        if (!dismissEvent.defaultPrevented) {
          setOpen(false);
        }
      }}
    >
      <div
        role="dialog"
        aria-modal="true"
        className={cn(
          "w-full max-w-lg rounded-2xl border border-border bg-background p-6 shadow-2xl",
          className,
        )}
        {...props}
      >
        {children}
      </div>
    </div>,
    document.body,
  );
}

export function DialogHeader({
  className,
  ...props
}: React.HTMLAttributes<HTMLDivElement>) {
  return <div className={cn("flex flex-col gap-2 text-left", className)} {...props} />;
}

export function DialogFooter({
  className,
  ...props
}: React.HTMLAttributes<HTMLDivElement>) {
  return <div className={cn("mt-6 flex justify-end gap-2", className)} {...props} />;
}

export function DialogTitle({
  className,
  ...props
}: React.HTMLAttributes<HTMLHeadingElement>) {
  return <h2 className={cn("text-xl font-semibold", className)} {...props} />;
}

export function DialogDescription({
  className,
  ...props
}: React.HTMLAttributes<HTMLParagraphElement>) {
  return <p className={cn("text-sm text-muted-foreground", className)} {...props} />;
}

export function DialogAction(props: React.ButtonHTMLAttributes<HTMLButtonElement>) {
  return <button type="button" {...props} />;
}

export function DialogCancel(props: React.ButtonHTMLAttributes<HTMLButtonElement>) {
  const { setOpen } = useDialogContext();
  return (
    <button
      type="button"
      {...props}
      onClick={(event) => {
        props.onClick?.(event);
        if (!event.defaultPrevented) {
          setOpen(false);
        }
      }}
    />
  );
}
