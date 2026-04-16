"use client";

import type { NavItem } from "@/types/navigation";
import { useAuthStore } from "@/store/auth-store";
import { useWorkspaceStore } from "@/store/workspace-store";

export interface QuickAction {
  id: string;
  label: string;
  shortcut?: string;
  href?: string;
  callback?: () => void;
}

export const NAV_ITEMS: NavItem[] = [
  {
    id: "home",
    label: "Home",
    icon: "LayoutDashboard",
    href: "/home",
    requiredRoles: [],
  },
  {
    id: "admin-settings",
    label: "Admin",
    icon: "Settings2",
    href: "/admin/settings",
    requiredRoles: ["platform_admin"],
  },
  {
    id: "agents",
    label: "Agents",
    icon: "Bot",
    href: "/agents",
    requiredRoles: ["agent_operator", "agent_viewer", "workspace_admin", "superadmin"],
  },
  {
    id: "fleet",
    label: "Fleet",
    icon: "Network",
    href: "/fleet",
    requiredRoles: ["agent_operator", "agent_viewer", "workspace_admin", "superadmin"],
  },
  {
    id: "workflows",
    label: "Workflows",
    icon: "Workflow",
    href: "/workflows",
    requiredRoles: ["workspace_editor", "workspace_admin", "superadmin"],
  },
  {
    id: "workflow-editor-monitor",
    label: "Workflow Studio",
    icon: "Workflow",
    href: "/workflow-editor-monitor",
    requiredRoles: ["workspace_editor", "workspace_admin", "superadmin"],
  },
  {
    id: "analytics",
    label: "Analytics",
    icon: "LineChart",
    href: "/analytics",
    requiredRoles: ["analytics_viewer", "workspace_admin", "superadmin"],
  },
  {
    id: "policies",
    label: "Policies",
    icon: "ShieldCheck",
    href: "/policies",
    requiredRoles: ["policy_manager", "superadmin"],
  },
  {
    id: "trust",
    label: "Trust",
    icon: "Fingerprint",
    href: "/trust",
    requiredRoles: ["trust_officer", "superadmin"],
  },
  {
    id: "trust-workbench",
    label: "Trust Workbench",
    icon: "Fingerprint",
    href: "/trust-workbench",
    requiredRoles: ["trust_certifier", "platform_admin", "superadmin"],
  },
  {
    id: "settings",
    label: "Settings",
    icon: "Settings2",
    href: "/settings",
    requiredRoles: ["workspace_admin", "superadmin"],
  },
];

export const QUICK_ACTIONS: QuickAction[] = [
  {
    id: "toggle-sidebar",
    label: "Toggle sidebar",
    shortcut: "Shift+B",
    callback: () => {
      const store = useWorkspaceStore.getState();
      store.setSidebarCollapsed(!store.sidebarCollapsed);
    },
  },
  {
    id: "component-showcase",
    label: "Open component showcase",
    shortcut: "Dev",
    href: "/dev/components",
  },
  {
    id: "sign-out",
    label: "Clear session and return to login",
    shortcut: "Shift+L",
    callback: () => {
      useAuthStore.getState().clearAuth();
      if (typeof window !== "undefined") {
        window.location.assign("/login");
      }
    },
  },
];
