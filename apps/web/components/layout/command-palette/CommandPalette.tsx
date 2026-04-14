"use client";

import { useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { Search } from "lucide-react";
import { Command, CommandDialog, CommandEmpty, CommandGroup, CommandInput, CommandItem, CommandList, CommandSeparator } from "@/components/ui/command";
import { NAV_ITEMS, QUICK_ACTIONS } from "@/components/layout/sidebar/nav-config";
import { useCommandPalette } from "@/components/layout/command-palette/CommandPaletteProvider";
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
  const roles = useAuthStore((state) => state.user?.roles ?? []);
  const [query, setQuery] = useState("");

  const items = useMemo(() => NAV_ITEMS.filter((item) => matchesRole(item.requiredRoles, roles)), [roles]);
  const normalizedQuery = query.trim().toLowerCase();
  const filteredNav = items.filter((item) => item.label.toLowerCase().includes(normalizedQuery));
  const filteredActions = QUICK_ACTIONS.filter((action) => action.label.toLowerCase().includes(normalizedQuery));

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
          {filteredNav.length === 0 && filteredActions.length === 0 ? (
            <CommandEmpty>No commands found.</CommandEmpty>
          ) : (
            <>
              <CommandGroup heading="Navigation">
                {filteredNav.map((item) => (
                  <CommandItem
                    key={item.id}
                    onClick={() => {
                      router.push(item.href);
                      setOpen(false);
                    }}
                  >
                    <span>{item.label}</span>
                    <span className="text-xs text-muted-foreground">{item.href}</span>
                  </CommandItem>
                ))}
              </CommandGroup>
              <CommandSeparator />
              <CommandGroup heading="Quick actions">
                {filteredActions.map((action) => (
                  <CommandItem
                    key={action.id}
                    onClick={() => {
                      if (action.href) {
                        router.push(action.href);
                      } else {
                        action.callback?.();
                      }
                      setOpen(false);
                    }}
                  >
                    <span>{action.label}</span>
                    {action.shortcut ? <span className="text-xs text-muted-foreground">{action.shortcut}</span> : null}
                  </CommandItem>
                ))}
              </CommandGroup>
            </>
          )}
        </CommandList>
      </Command>
    </CommandDialog>
  );
}
