"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { Bot, ChevronLeft, ChevronRight, Fingerprint, LayoutDashboard, LineChart, Settings2, ShieldCheck, Workflow } from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { useAuthStore } from "@/store/auth-store";
import { useWorkspaceStore } from "@/store/workspace-store";
import { NAV_ITEMS } from "@/components/layout/sidebar/nav-config";

const iconMap = {
  LayoutDashboard,
  Bot,
  Workflow,
  LineChart,
  ShieldCheck,
  Fingerprint,
  Settings2,
} as const;

function canView(requiredRoles: string[], userRoles: string[]): boolean {
  if (userRoles.includes("superadmin")) {
    return true;
  }
  if (requiredRoles.length === 0) {
    return true;
  }
  return requiredRoles.some((role) => userRoles.includes(role));
}

export function Sidebar() {
  const pathname = usePathname();
  const user = useAuthStore((state) => state.user);
  const sidebarCollapsed = useWorkspaceStore((state) => state.sidebarCollapsed);
  const setSidebarCollapsed = useWorkspaceStore((state) => state.setSidebarCollapsed);
  const userRoles = user?.roles ?? [];
  const visibleItems = NAV_ITEMS.filter((item) => canView(item.requiredRoles, userRoles));

  return (
    <aside
      className={cn(
        "flex h-screen flex-col border-r border-border/80 bg-sidebar text-sidebar-foreground transition-[width] duration-200",
        sidebarCollapsed ? "w-16" : "w-[260px]",
      )}
    >
      <div className={cn("border-b border-border/70 px-3 py-4", sidebarCollapsed ? "items-center" : "")}>
        <div className={cn("flex items-center gap-3", sidebarCollapsed && "justify-center")}>
          <div className="rounded-2xl bg-brand-primary/10 p-2 text-brand-primary">
            <Bot className="h-5 w-5" />
          </div>
          {!sidebarCollapsed ? (
            <div className="animate-sidebar-in">
              <p className="text-xs font-semibold uppercase tracking-[0.24em] text-brand-accent">Musematic</p>
              <p className="text-base font-semibold">Agentic Mesh</p>
            </div>
          ) : null}
        </div>
      </div>
      <nav className="flex-1 space-y-1 px-2 py-4" aria-label="Main navigation">
        {visibleItems.map((item) => {
          const Icon = iconMap[item.icon as keyof typeof iconMap] ?? LayoutDashboard;
          const isActive = pathname === item.href || (item.href !== "/" && pathname.startsWith(`${item.href}/`));

          return (
            <Link
              key={item.id}
              aria-current={isActive ? "page" : undefined}
              className={cn(
                "flex items-center gap-3 rounded-xl px-3 py-2 text-sm font-medium transition-colors hover:bg-sidebar-accent/80",
                isActive && "bg-sidebar-accent text-foreground",
                sidebarCollapsed && "justify-center px-0",
              )}
              href={item.href}
              title={sidebarCollapsed ? item.label : undefined}
            >
              <Icon className="h-4 w-4 shrink-0" />
              {!sidebarCollapsed ? <span className="truncate">{item.label}</span> : null}
            </Link>
          );
        })}
      </nav>
      <div className="border-t border-border/70 p-2">
        <Button
          className={cn("w-full", sidebarCollapsed ? "px-0" : "justify-between")}
          data-testid="sidebar-toggle"
          size={sidebarCollapsed ? "icon" : "default"}
          variant="ghost"
          onClick={() => setSidebarCollapsed(!sidebarCollapsed)}
        >
          {!sidebarCollapsed ? <span>Collapse</span> : null}
          {sidebarCollapsed ? <ChevronRight className="h-4 w-4" /> : <ChevronLeft className="h-4 w-4" />}
        </Button>
      </div>
    </aside>
  );
}
