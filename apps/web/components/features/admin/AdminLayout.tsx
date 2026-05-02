"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  Activity,
  Bell,
  CreditCard,
  Database,
  HeartPulse,
  KeyRound,
  LifeBuoy,
  Lock,
  Menu,
  Search,
  Settings,
  ShieldCheck,
  Users,
} from "lucide-react";
import { useCommandPalette } from "@/components/layout/command-palette/CommandPaletteProvider";
import { ThemeToggle } from "@/components/layout/theme-toggle/ThemeToggle";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { ImpersonationBanner } from "@/components/features/admin/ImpersonationBanner";
import { ReadOnlyIndicator } from "@/components/features/admin/ReadOnlyIndicator";
import { useAdminStore } from "@/lib/stores/admin-store";
import { cn } from "@/lib/utils";

interface AdminLayoutProps {
  children: React.ReactNode;
  isSuperAdmin: boolean;
}

const sections = [
  {
    label: "Identity",
    icon: Users,
    items: [
      ["/admin/users", "Users"],
      ["/admin/roles", "Roles"],
      ["/admin/groups", "Groups"],
      ["/admin/sessions", "Sessions"],
      ["/admin/oauth-providers", "OAuth"],
      ["/admin/ibor", "IBOR"],
      ["/admin/api-keys", "API keys"],
    ],
  },
  {
    label: "Tenancy",
    icon: Database,
    items: [
      ["/admin/tenants", "Tenants", "superadmin"],
      ["/admin/workspaces", "Workspaces"],
      ["/admin/namespaces", "Namespaces"],
    ],
  },
  {
    label: "Configuration",
    icon: Settings,
    items: [
      ["/admin/settings", "Settings"],
      ["/admin/feature-flags", "Feature flags"],
      ["/admin/model-catalog", "Models"],
      ["/admin/policies", "Policies"],
      ["/admin/connectors", "Connectors"],
    ],
  },
  {
    label: "Security",
    icon: ShieldCheck,
    items: [
      ["/admin/audit-chain", "Audit chain"],
      ["/admin/security/sbom", "SBOM"],
      ["/admin/security/pentests", "Pentests"],
      ["/admin/security/rotations", "Rotations"],
      ["/admin/security/jit", "JIT"],
      ["/admin/privacy/dsr", "DSR"],
      ["/admin/privacy/dlp", "DLP"],
      ["/admin/privacy/pia", "PIA"],
      ["/admin/compliance", "Compliance"],
      ["/admin/privacy/consent", "Consent"],
    ],
  },
  {
    label: "Operations",
    icon: HeartPulse,
    items: [
      ["/admin/health", "Health"],
      ["/admin/incidents", "Incidents"],
      ["/admin/runbooks", "Runbooks"],
      ["/admin/maintenance", "Maintenance"],
      ["/admin/regions", "Regions", "superadmin"],
      ["/admin/queues", "Queues"],
      ["/admin/warm-pool", "Warm pool"],
      ["/admin/executions", "Executions"],
    ],
  },
  {
    label: "Cost",
    icon: CreditCard,
    items: [
      ["/admin/costs/overview", "Overview"],
      ["/admin/subscriptions", "Subscriptions"],
      ["/admin/costs/budgets", "Budgets"],
      ["/admin/costs/chargeback", "Chargeback"],
      ["/admin/costs/anomalies", "Anomalies"],
      ["/admin/costs/forecasts", "Forecasts"],
      ["/admin/costs/rates", "Rates"],
    ],
  },
  {
    label: "Observability",
    icon: Activity,
    items: [
      ["/admin/observability/dashboards", "Dashboards"],
      ["/admin/observability/alerts", "Alerts"],
      ["/admin/observability/log-retention", "Retention"],
      ["/admin/observability/registry", "Registry"],
    ],
  },
  {
    label: "Integrations",
    icon: KeyRound,
    items: [
      ["/admin/integrations/webhooks", "Webhooks"],
      ["/admin/integrations/incidents", "Incidents"],
      ["/admin/integrations/notifications", "Notifications"],
      ["/admin/integrations/a2a", "A2A"],
      ["/admin/integrations/mcp", "MCP"],
    ],
  },
  {
    label: "Lifecycle",
    icon: Lock,
    items: [
      ["/admin/lifecycle/version", "Version", "superadmin"],
      ["/admin/lifecycle/migrations", "Migrations", "superadmin"],
      ["/admin/lifecycle/backup", "Backup", "superadmin"],
      ["/admin/lifecycle/installer", "Installer", "superadmin"],
    ],
  },
  {
    label: "Audit",
    icon: LifeBuoy,
    items: [
      ["/admin/audit", "Query"],
      ["/admin/audit/admin-activity", "Activity"],
    ],
  },
] as const;

export function AdminLayout({ children, isSuperAdmin }: AdminLayoutProps) {
  const pathname = usePathname();
  const { toggle: toggleCommandPalette } = useCommandPalette();
  const incrementTwoPaNotifications = useAdminStore((state) => state.incrementTwoPaNotifications);
  const twoPaCount = useAdminStore((state) => state.twoPersonAuthNotificationsCount);
  const [pendingTwoPaRequests, setPendingTwoPaRequests] = useState<
    Array<{ id: string; action: string }>
  >([]);

  useEffect(() => {
    const baseWsUrl = process.env.NEXT_PUBLIC_WS_URL;
    if (!baseWsUrl || typeof window === "undefined") {
      return undefined;
    }

    const socket = new WebSocket(`${baseWsUrl}/api/v1/ws?channel=ADMIN_HEALTH`);
    socket.onmessage = (event) => {
      let payload: {
        event_type?: string;
        request_id?: string;
        action?: string;
      };
      try {
        payload = JSON.parse(String(event.data)) as {
          event_type?: string;
          request_id?: string;
          action?: string;
        };
      } catch {
        return;
      }
      if (payload.event_type !== "admin.2pa.requested") {
        return;
      }
      const id = payload.request_id ?? crypto.randomUUID();
      setPendingTwoPaRequests((current) => [
        { id, action: payload.action ?? "admin action" },
        ...current.filter((item) => item.id !== id),
      ]);
      incrementTwoPaNotifications();
    };
    return () => socket.close();
  }, [incrementTwoPaNotifications]);

  return (
    <div className="min-h-screen bg-background">
      <ImpersonationBanner />
      <div className="grid min-h-screen lg:grid-cols-[280px_minmax(0,1fr)]">
        <aside className="hidden border-r bg-sidebar text-sidebar-foreground lg:block">
          <div className="sticky top-0 flex h-screen flex-col">
            <div className="flex h-14 items-center gap-2 border-b px-4">
              <ShieldCheck className="h-5 w-5 text-primary" />
              <Link href="/admin" className="font-semibold">
                Musematic Admin
              </Link>
            </div>
            <nav className="min-h-0 flex-1 overflow-y-auto px-3 py-4">
              {sections.map((section) => (
                <div key={section.label} className="mb-5">
                  <div className="mb-2 flex items-center gap-2 px-2 text-xs font-semibold uppercase text-muted-foreground">
                    <section.icon className="h-4 w-4" />
                    {section.label}
                  </div>
                  <div className="space-y-1">
                    {section.items
                      .filter((item) => item[2] !== "superadmin" || isSuperAdmin)
                      .map(([href, label]) => (
                        <Link
                          key={href}
                          href={href}
                          className={cn(
                            "block rounded-md px-3 py-2 text-sm transition-colors hover:bg-sidebar-accent",
                            pathname === href && "bg-sidebar-accent font-medium text-primary",
                          )}
                        >
                          {label}
                        </Link>
                      ))}
                  </div>
                </div>
              ))}
            </nav>
          </div>
        </aside>
        <div className="min-w-0">
          <header className="sticky top-0 z-10 flex h-14 items-center justify-between border-b bg-background/95 px-4 backdrop-blur">
            <div className="flex min-w-0 items-center gap-2">
              <Button variant="ghost" size="icon" className="lg:hidden" aria-label="Open menu">
                <Menu className="h-4 w-4" />
              </Button>
              <Badge variant="outline" className="rounded-md">
                {isSuperAdmin ? "Super admin" : "Admin"}
              </Badge>
              <ReadOnlyIndicator />
            </div>
            <div className="flex items-center gap-2">
              <Button
                variant="ghost"
                size="icon"
                aria-label="Search admin"
                onClick={toggleCommandPalette}
              >
                <Search className="h-4 w-4" />
              </Button>
              <DropdownMenu>
                <DropdownMenuTrigger asChild>
                  <Button variant="ghost" size="icon" aria-label="2PA requests" className="relative">
                    <Bell className="h-4 w-4" />
                    {twoPaCount > 0 ? (
                      <span className="absolute right-1 top-1 h-2 w-2 rounded-full bg-destructive" />
                    ) : null}
                  </Button>
                </DropdownMenuTrigger>
                <DropdownMenuContent align="end" className="w-80">
                  <DropdownMenuLabel>Pending 2PA requests</DropdownMenuLabel>
                  {pendingTwoPaRequests.length === 0 ? (
                    <div className="px-2 py-3 text-sm text-muted-foreground">
                      No pending approval requests.
                    </div>
                  ) : (
                    pendingTwoPaRequests.map((request) => (
                      <DropdownMenuItem
                        key={request.id}
                        onClick={() => window.location.assign(`/admin/regions?twoPaRequest=${request.id}`)}
                      >
                        <span className="min-w-0 truncate">{request.action}</span>
                      </DropdownMenuItem>
                    ))
                  )}
                </DropdownMenuContent>
              </DropdownMenu>
              <Button asChild variant="ghost" size="icon" aria-label="Admin help">
                <Link href="/admin/runbooks">
                  <LifeBuoy className="h-4 w-4" />
                </Link>
              </Button>
              <ThemeToggle />
            </div>
          </header>
          <main className="mx-auto w-full max-w-[1600px] px-4 py-5 sm:px-6">{children}</main>
        </div>
      </div>
    </div>
  );
}
