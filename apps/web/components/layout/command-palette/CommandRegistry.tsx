"use client";

import * as React from "react";

export interface RegisteredCommand {
  id: string;
  label: string;
  category: string;
  description?: string;
  href?: string;
  shortcut?: string;
  keywords?: string[];
  action?: () => void | Promise<void>;
}

interface CommandRegistryContextValue {
  commands: RegisteredCommand[];
  registerCommands: (commands: RegisteredCommand[]) => () => void;
}

const CommandRegistryContext = React.createContext<CommandRegistryContextValue | null>(null);

export function CommandRegistryProvider({ children }: React.PropsWithChildren) {
  const [groups, setGroups] = React.useState<Map<string, RegisteredCommand[]>>(() => new Map());

  const registerCommands = React.useCallback((commands: RegisteredCommand[]) => {
    const token =
      typeof crypto !== "undefined" && "randomUUID" in crypto
        ? crypto.randomUUID()
        : `commands-${Date.now()}-${Math.random()}`;
    setGroups((current) => {
      const next = new Map(current);
      next.set(token, commands);
      return next;
    });

    return () => {
      setGroups((current) => {
        const next = new Map(current);
        next.delete(token);
        return next;
      });
    };
  }, []);

  const commands = React.useMemo(
    () => Array.from(groups.values()).flat(),
    [groups],
  );

  const value = React.useMemo(
    () => ({ commands, registerCommands }),
    [commands, registerCommands],
  );

  return (
    <CommandRegistryContext.Provider value={value}>
      {children}
    </CommandRegistryContext.Provider>
  );
}

export function useCommandRegistry(): CommandRegistryContextValue {
  const context = React.useContext(CommandRegistryContext);
  if (!context) {
    throw new Error("useCommandRegistry must be used inside CommandRegistryProvider");
  }
  return context;
}

export function useRegisterCommands(commands: RegisteredCommand[]) {
  const { registerCommands } = useCommandRegistry();
  const signature = React.useMemo(
    () =>
      commands
        .map((command) => `${command.id}:${command.label}:${command.shortcut ?? ""}`)
        .join("|"),
    [commands],
  );
  const stableCommands = React.useMemo(() => commands, [signature]);

  React.useEffect(() => registerCommands(stableCommands), [registerCommands, stableCommands]);
}

const RESERVED_SHORTCUTS = new Set([
  "cmd+t",
  "cmd+w",
  "cmd+q",
  "cmd+r",
  "cmd+l",
  "cmd+n",
  "ctrl+t",
  "ctrl+w",
  "ctrl+r",
  "ctrl+l",
  "ctrl+n",
  "alt+f4",
]);

export function normalizeShortcut(shortcut: string): string {
  return shortcut
    .trim()
    .toLowerCase()
    .replace(/\s+/g, "")
    .replace("meta+", "cmd+")
    .replace("command+", "cmd+")
    .replace("control+", "ctrl+");
}

export function isReservedShortcut(shortcut: string): boolean {
  return RESERVED_SHORTCUTS.has(normalizeShortcut(shortcut));
}

export function validateShortcutBinding(shortcut: string): { ok: true } | { ok: false; reason: string } {
  if (isReservedShortcut(shortcut)) {
    return {
      ok: false,
      reason: "That shortcut is reserved by the browser or operating system.",
    };
  }
  return { ok: true };
}

export function isEditableTarget(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) {
    return false;
  }
  const tagName = target.tagName.toLowerCase();
  return tagName === "input" || tagName === "textarea" || target.isContentEditable;
}

export function commandMatches(command: RegisteredCommand, query: string): boolean {
  const normalized = query.trim().toLowerCase();
  if (!normalized) {
    return true;
  }
  const haystack = [
    command.label,
    command.description,
    command.category,
    command.href,
    command.shortcut,
    ...(command.keywords ?? []),
  ]
    .filter(Boolean)
    .join(" ")
    .toLowerCase();
  return normalized
    .split(/\s+/)
    .every((part) => haystack.includes(part));
}
