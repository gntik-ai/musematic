"use client";

import { Bell, Command as CommandIcon, MoonStar, SunMedium } from "lucide-react";
import { useTheme } from "next-themes";
import { Breadcrumb } from "@/components/layout/breadcrumb/Breadcrumb";
import { useCommandPalette } from "@/components/layout/command-palette/CommandPaletteProvider";
import { ConnectionIndicator } from "@/components/layout/header/ConnectionIndicator";
import { UserMenu } from "@/components/layout/header/UserMenu";
import { WorkspaceSelector } from "@/components/layout/header/WorkspaceSelector";
import { Button } from "@/components/ui/button";

export function Header() {
  const { toggle } = useCommandPalette();
  const { resolvedTheme, setTheme } = useTheme();

  return (
    <header className="sticky top-0 z-30 flex h-16 items-center justify-between gap-4 border-b border-border/70 bg-background/80 px-6 backdrop-blur">
      <div className="min-w-0 flex-1">
        <WorkspaceSelector />
      </div>
      <div className="hidden min-w-0 flex-[1.5] justify-center lg:flex">
        <Breadcrumb />
      </div>
      <div className="flex flex-1 items-center justify-end gap-3">
        <ConnectionIndicator />
        <Button className="gap-2" data-testid="command-palette-toggle" variant="outline" onClick={toggle}>
          <CommandIcon className="h-4 w-4" />
          <span className="hidden md:inline">Command</span>
          <span className="rounded border border-border px-1.5 py-0.5 text-[10px] font-semibold text-muted-foreground">⌘K</span>
        </Button>
        <Button
          data-testid="theme-toggle"
          size="icon"
          variant="ghost"
          onClick={() => setTheme(resolvedTheme === "dark" ? "light" : "dark")}
        >
          {resolvedTheme === "dark" ? <SunMedium className="h-4 w-4" /> : <MoonStar className="h-4 w-4" />}
        </Button>
        <Button size="icon" variant="ghost">
          <Bell className="h-4 w-4" />
        </Button>
        <UserMenu />
      </div>
    </header>
  );
}
