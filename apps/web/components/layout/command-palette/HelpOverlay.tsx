"use client";

import { useMemo } from "react";
import { Keyboard, X } from "lucide-react";
import { useCommandRegistry } from "@/components/layout/command-palette/CommandRegistry";
import { Button } from "@/components/ui/button";

interface HelpOverlayProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

function displayShortcut(shortcut: string): string {
  if (typeof navigator !== "undefined" && /Mac|iPhone|iPad/.test(navigator.platform)) {
    return shortcut.replace(/Cmd/g, "⌘").replace(/Ctrl/g, "⌃").replace(/Shift/g, "⇧");
  }
  return shortcut.replace(/Cmd/g, "Ctrl");
}

export function HelpOverlay({ open, onOpenChange }: HelpOverlayProps) {
  const { commands } = useCommandRegistry();
  const groupedCommands = useMemo(() => {
    const groups = new Map<string, typeof commands>();
    for (const command of commands) {
      const existing = groups.get(command.category) ?? [];
      existing.push(command);
      groups.set(command.category, existing);
    }
    return Array.from(groups.entries()).map(([category, items]) => ({
      category,
      items: items.filter((item) => item.shortcut).sort((left, right) => left.label.localeCompare(right.label)),
    }));
  }, [commands]);

  if (!open) {
    return null;
  }

  return (
    <div
      aria-labelledby="command-help-title"
      aria-modal="true"
      className="fixed inset-0 z-[60] flex items-start justify-center bg-black/55 px-4 pt-20"
      role="dialog"
      onClick={() => onOpenChange(false)}
    >
      <div
        className="w-full max-w-3xl rounded-xl border border-border bg-popover p-5 text-popover-foreground shadow-2xl"
        onClick={(event) => event.stopPropagation()}
      >
        <div className="flex items-center justify-between gap-4">
          <div className="flex items-center gap-3">
            <Keyboard className="h-5 w-5 text-brand-accent" />
            <div>
              <h2 id="command-help-title" className="text-lg font-semibold">
                Keyboard shortcuts
              </h2>
              <p className="text-sm text-muted-foreground">
                Commands registered for the current page and platform shell.
              </p>
            </div>
          </div>
          <Button aria-label="Close keyboard shortcuts" size="icon" variant="ghost" onClick={() => onOpenChange(false)}>
            <X className="h-4 w-4" />
          </Button>
        </div>
        <div className="mt-5 grid gap-4 md:grid-cols-2">
          {groupedCommands.map(({ category, items }) =>
            items.length > 0 ? (
              <section key={category} className="rounded-lg border border-border p-4">
                <h3 className="text-sm font-semibold">{category}</h3>
                <dl className="mt-3 space-y-3">
                  {items.map((command) => (
                    <div key={command.id} className="flex items-center justify-between gap-3">
                      <dt className="min-w-0">
                        <p className="truncate text-sm font-medium">{command.label}</p>
                        {command.description ? (
                          <p className="truncate text-xs text-muted-foreground">{command.description}</p>
                        ) : null}
                      </dt>
                      <dd className="shrink-0 rounded border border-border bg-muted px-2 py-1 font-mono text-xs">
                        {displayShortcut(command.shortcut ?? "")}
                      </dd>
                    </div>
                  ))}
                </dl>
              </section>
            ) : null,
          )}
        </div>
      </div>
    </div>
  );
}
