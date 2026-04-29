"use client";

import * as React from "react";
import {
  CommandRegistryProvider,
  isEditableTarget,
} from "@/components/layout/command-palette/CommandRegistry";
import { HelpOverlay } from "@/components/layout/command-palette/HelpOverlay";

interface CommandPaletteContextValue {
  open: boolean;
  setOpen: (open: boolean) => void;
  toggle: () => void;
  helpOpen: boolean;
  setHelpOpen: (open: boolean) => void;
  openHelp: () => void;
}

const CommandPaletteContext = React.createContext<CommandPaletteContextValue | null>(null);

export function CommandPaletteProvider({ children }: React.PropsWithChildren) {
  const [open, setOpen] = React.useReducer((_state: boolean, nextState: boolean) => nextState, false);
  const [helpOpen, setHelpOpen] = React.useReducer((_state: boolean, nextState: boolean) => nextState, false);

  React.useEffect(() => {
    const handler = (event: KeyboardEvent) => {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        setOpen(true);
      }
      if (event.key === "?" && !isEditableTarget(event.target)) {
        event.preventDefault();
        setHelpOpen(true);
      }
      if (event.key === "Escape") {
        setOpen(false);
        setHelpOpen(false);
      }
    };

    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, []);

  const value = React.useMemo(
    () => ({
      open,
      setOpen,
      toggle: () => setOpen(!open),
      helpOpen,
      setHelpOpen,
      openHelp: () => setHelpOpen(true),
    }),
    [helpOpen, open],
  );

  return (
    <CommandRegistryProvider>
      <CommandPaletteContext.Provider value={value}>
        {children}
        <HelpOverlay open={helpOpen} onOpenChange={setHelpOpen} />
      </CommandPaletteContext.Provider>
    </CommandRegistryProvider>
  );
}

export function useCommandPalette(): CommandPaletteContextValue {
  const context = React.useContext(CommandPaletteContext);
  if (!context) {
    throw new Error("useCommandPalette must be used inside CommandPaletteProvider");
  }
  return context;
}
