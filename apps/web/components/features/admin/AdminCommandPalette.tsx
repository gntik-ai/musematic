"use client";

import { useRouter } from "next/navigation";
import { Search } from "lucide-react";
import {
  Command,
  CommandDialog,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
  CommandSeparator,
} from "@/components/ui/command";
import { useCommandPalette } from "@/components/layout/command-palette/CommandPaletteProvider";
import { useAuthStore } from "@/store/auth-store";

const results = [
  {
    category: "Identity",
    items: [
      ["Users", "/admin/users", "users identity access"],
      ["Roles", "/admin/roles", "permissions rbac"],
      ["Groups", "/admin/groups", "groups mapping"],
      ["Sessions", "/admin/sessions", "active sessions"],
    ],
  },
  {
    category: "Operations",
    items: [
      ["Workspaces", "/admin/workspaces", "tenant workspaces"],
      ["Executions", "/admin/executions", "runs jobs execution ids"],
      ["Incidents", "/admin/incidents", "alerts incident response"],
      ["Health", "/admin/health", "status grafana observability"],
    ],
  },
  {
    category: "Configuration",
    items: [
      ["Settings", "/admin/settings", "platform settings"],
      ["Feature flags", "/admin/feature-flags", "flags rollouts"],
      ["Model catalog", "/admin/model-catalog", "models providers"],
      ["Connectors", "/admin/connectors", "plugins integrations"],
    ],
  },
  {
    category: "Audit",
    items: [
      ["Audit query", "/admin/audit", "logs chain events"],
      ["Admin activity", "/admin/audit/admin-activity", "admin events"],
      ["Audit chain", "/admin/audit-chain", "integrity verification"],
    ],
  },
] as const;

const superAdminResults = [
  {
    category: "Super Admin",
    items: [
      ["Tenants", "/admin/tenants", "tenant management"],
      ["Regions", "/admin/regions", "failover replication"],
      ["Lifecycle installer", "/admin/lifecycle/installer", "export import backup"],
      ["Migrations", "/admin/lifecycle/migrations", "database migrations"],
    ],
  },
] as const;

export function AdminCommandPalette() {
  const router = useRouter();
  const { open, setOpen } = useCommandPalette();
  const roles = useAuthStore((state) => state.user?.roles ?? []);
  const isSuperAdmin = roles.includes("superadmin");
  const groups = isSuperAdmin ? [...results, ...superAdminResults] : results;

  function navigate(href: string) {
    router.push(href);
    setOpen(false);
  }

  return (
    <CommandDialog open={open} onOpenChange={setOpen}>
      <Command>
        <div className="flex items-center gap-2">
          <Search className="h-4 w-4 text-muted-foreground" />
          <CommandInput placeholder="Search users, workspaces, executions, audit entries, or settings" />
        </div>
        <CommandList>
          <CommandEmpty>No admin results found.</CommandEmpty>
          {groups.map((group, index) => (
            <div key={group.category}>
              {index > 0 ? <CommandSeparator /> : null}
              <CommandGroup heading={group.category}>
                {group.items.map(([label, href]) => (
                  <CommandItem
                    key={href}
                    onClick={() => navigate(href)}
                  >
                    <span className="truncate">{label}</span>
                    <span className="ml-auto truncate text-xs text-muted-foreground">{href}</span>
                  </CommandItem>
                ))}
              </CommandGroup>
            </div>
          ))}
        </CommandList>
      </Command>
    </CommandDialog>
  );
}
