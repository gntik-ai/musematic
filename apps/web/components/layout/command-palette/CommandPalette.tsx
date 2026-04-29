"use client";

import { useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { Search } from "lucide-react";
import { Command, CommandDialog, CommandEmpty, CommandGroup, CommandInput, CommandItem, CommandList, CommandSeparator } from "@/components/ui/command";
import { NAV_ITEMS, QUICK_ACTIONS } from "@/components/layout/sidebar/nav-config";
import { useCommandPalette } from "@/components/layout/command-palette/CommandPaletteProvider";
import {
  commandMatches,
  useCommandRegistry,
  type RegisteredCommand,
} from "@/components/layout/command-palette/CommandRegistry";
import { useAuthStore } from "@/store/auth-store";

function matchesRole(requiredRoles: string[], roles: string[]): boolean {
  if (roles.includes("superadmin")) {
    return true;
  }
  if (requiredRoles.length === 0) {
    return true;
  }
  return requiredRoles.some((role) => roles.includes(role));
}

export function CommandPalette() {
  const router = useRouter();
  const { open, setOpen } = useCommandPalette();
  const { commands } = useCommandRegistry();
  const roles = useAuthStore((state) => state.user?.roles ?? []);
  const [query, setQuery] = useState("");

  const items = useMemo(() => NAV_ITEMS.filter((item) => matchesRole(item.requiredRoles, roles)), [roles]);
  const navCommands = useMemo<RegisteredCommand[]>(
    () =>
      items.map((item) => ({
        id: `nav.${item.id}`,
        label: item.label,
        category: "Navigation",
        href: item.href,
        keywords: [item.id],
      })),
    [items],
  );
  const quickActionCommands = useMemo<RegisteredCommand[]>(
    () =>
      QUICK_ACTIONS.map((action) => ({
        id: `quick.${action.id}`,
        label: action.label,
        category: "Quick actions",
        ...(action.href ? { href: action.href } : {}),
        ...(action.shortcut ? { shortcut: action.shortcut } : {}),
        ...(action.callback ? { action: action.callback } : {}),
      })),
    [],
  );
  const filteredCommands = useMemo(() => {
    const seen = new Set<string>();
    const allCommands = [...commands, ...navCommands, ...quickActionCommands].filter((command) => {
      if (seen.has(command.id)) {
        return false;
      }
      seen.add(command.id);
      return commandMatches(command, query);
    });
    const groups = new Map<string, RegisteredCommand[]>();
    for (const command of allCommands) {
      const existing = groups.get(command.category) ?? [];
      existing.push(command);
      groups.set(command.category, existing);
    }
    return Array.from(groups.entries());
  }, [commands, navCommands, query, quickActionCommands]);

  function runCommand(command: RegisteredCommand) {
    if (command.href) {
      router.push(command.href);
    } else {
      void command.action?.();
    }
    setOpen(false);
  }

  return (
    <CommandDialog open={open} onOpenChange={setOpen}>
      <Command>
        <div className="flex items-center gap-3">
          <Search className="h-4 w-4 text-muted-foreground" />
          <CommandInput
            aria-label="Command palette search"
            data-testid="command-input"
            placeholder="Jump to routes or trigger quick actions"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
          />
        </div>
        <CommandList>
          {filteredCommands.length === 0 ? (
            <CommandEmpty>No commands found.</CommandEmpty>
          ) : (
            <>
              {filteredCommands.map(([category, group], index) => (
                <div key={category}>
                  {index > 0 ? <CommandSeparator /> : null}
                  <CommandGroup heading={category}>
                    {group.map((command) => (
                      <CommandItem key={command.id} onClick={() => runCommand(command)}>
                        <span className="min-w-0">
                          <span className="block truncate">{command.label}</span>
                          {command.description ? (
                            <span className="block truncate text-xs text-muted-foreground">{command.description}</span>
                          ) : null}
                        </span>
                        <span className="ml-3 shrink-0 text-xs text-muted-foreground">
                          {command.shortcut ?? command.href}
                        </span>
                      </CommandItem>
                    ))}
                  </CommandGroup>
                </div>
              ))}
            </>
          )}
        </CommandList>
      </Command>
    </CommandDialog>
  );
}
