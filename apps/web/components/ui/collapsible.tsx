import * as React from "react";

interface CollapsibleContextValue {
  open: boolean;
  setOpen: (open: boolean) => void;
}

const CollapsibleContext = React.createContext<CollapsibleContextValue | null>(null);

function useCollapsibleContext(): CollapsibleContextValue {
  const context = React.useContext(CollapsibleContext);
  if (!context) {
    throw new Error("Collapsible components must be wrapped in Collapsible");
  }
  return context;
}

export function Collapsible({
  children,
  defaultOpen = false,
  open: openProp,
  onOpenChange,
}: React.PropsWithChildren<{
  defaultOpen?: boolean;
  open?: boolean;
  onOpenChange?: (open: boolean) => void;
}>) {
  const [internalOpen, setInternalOpen] = React.useState(defaultOpen);
  const open = openProp ?? internalOpen;
  const setOpen = (nextOpen: boolean) => {
    if (openProp === undefined) {
      setInternalOpen(nextOpen);
    }
    onOpenChange?.(nextOpen);
  };

  return (
    <CollapsibleContext.Provider value={{ open, setOpen }}>
      <div>{children}</div>
    </CollapsibleContext.Provider>
  );
}

export function CollapsibleTrigger({
  children,
  ...props
}: React.ButtonHTMLAttributes<HTMLButtonElement>) {
  const { open, setOpen } = useCollapsibleContext();
  return (
    <button {...props} type="button" onClick={() => setOpen(!open)}>
      {children}
    </button>
  );
}

export function CollapsibleContent({ children }: React.PropsWithChildren) {
  const { open } = useCollapsibleContext();
  if (!open) {
    return null;
  }
  return <div>{children}</div>;
}
