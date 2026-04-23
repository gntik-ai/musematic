"use client";

import { Command as CommandIcon, Menu, MoonStar, SunMedium } from "lucide-react";
import { useTheme } from "next-themes";
import { Breadcrumb } from "@/components/layout/breadcrumb/Breadcrumb";
import { useCommandPalette } from "@/components/layout/command-palette/CommandPaletteProvider";
import { ConnectionIndicator } from "@/components/layout/header/ConnectionIndicator";
import { NotificationBell } from "@/components/features/alerts/notification-bell";
import { UserMenu } from "@/components/layout/header/UserMenu";
import { WorkspaceSelector } from "@/components/layout/header/WorkspaceSelector";
import { Button } from "@/components/ui/button";

interface HeaderProps {
  onOpenMobileNav: () => void;
}

export function Header({ onOpenMobileNav }: HeaderProps) {
  const { toggle } = useCommandPalette();
  const { resolvedTheme, setTheme } = useTheme();

  return (
    <header className="sticky top-0 z-30 flex min-h-16 flex-wrap items-center gap-3 border-b border-border/70 bg-background/80 px-4 py-3 backdrop-blur sm:px-6">
      <div className="flex min-w-0 flex-1 items-center gap-2">
        <Button
          aria-label="Open navigation"
          className="lg:hidden"
          size="icon"
          variant="outline"
          onClick={onOpenMobileNav}
        >
          <Menu className="h-4 w-4" />
        </Button>
        <div className="min-w-0 flex-1">
          <WorkspaceSelector />
        </div>
      </div>
      <div className="hidden min-w-0 flex-[1.5] justify-center lg:flex">
        <Breadcrumb />
      </div>
      <div className="ml-auto flex min-w-0 items-center justify-end gap-2 sm:gap-3">
        <div className="hidden sm:flex">
          <ConnectionIndicator />
        </div>
        <Button className="gap-2 px-2 sm:px-4" data-testid="command-palette-toggle" variant="outline" onClick={toggle}>
          <CommandIcon className="h-4 w-4" />
          <span className="hidden md:inline">Command</span>
          <span className="hidden sm:inline rounded border border-border px-1.5 py-0.5 text-[10px] font-semibold text-muted-foreground">⌘K</span>
        </Button>
        <Button
          data-testid="theme-toggle"
          size="icon"
          variant="ghost"
          onClick={() => setTheme(resolvedTheme === "dark" ? "light" : "dark")}
        >
          {resolvedTheme === "dark" ? <SunMedium className="h-4 w-4" /> : <MoonStar className="h-4 w-4" />}
        </Button>
        <NotificationBell />
        <UserMenu />
      </div>
      <div className="w-full lg:hidden">
        <Breadcrumb />
      </div>
    </header>
  );
}
