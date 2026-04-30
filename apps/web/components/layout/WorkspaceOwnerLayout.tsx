"use client";

import Link from "next/link";
import type { ReactNode } from "react";
import { useParams, usePathname } from "next/navigation";
import {
  BarChart3,
  DatabaseZap,
  Eye,
  Gauge,
  PlugZap,
  Settings2,
  Tags,
  UsersRound,
} from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

const navItems = [
  { label: "Dashboard", href: "", icon: BarChart3 },
  { label: "Members", href: "members", icon: UsersRound },
  { label: "Settings", href: "settings", icon: Settings2 },
  { label: "Connectors", href: "connectors", icon: PlugZap },
  { label: "Quotas", href: "quotas", icon: Gauge },
  { label: "Tags", href: "tags", icon: Tags },
  { label: "Visibility", href: "visibility", icon: Eye },
] as const;

export function WorkspaceOwnerLayout({
  children,
  title,
  description,
}: {
  children: ReactNode;
  title: string;
  description?: string;
}) {
  const params = useParams<{ id: string }>();
  const pathname = usePathname();
  const workspaceId = params.id;
  const basePath = `/workspaces/${workspaceId}`;

  return (
    <section className="space-y-6">
      <div className="flex flex-col gap-4 border-b pb-5 lg:flex-row lg:items-end lg:justify-between">
        <div className="space-y-2">
          <Badge className="w-fit" variant="outline">
            Workspace owner
          </Badge>
          <div>
            <h1 className="text-2xl font-semibold tracking-tight">{title}</h1>
            {description ? (
              <p className="mt-2 max-w-3xl text-sm text-muted-foreground">{description}</p>
            ) : null}
          </div>
        </div>
        <div className="flex items-center gap-2 text-xs text-muted-foreground">
          <DatabaseZap className="h-4 w-4" />
          <span className="max-w-[240px] truncate">{workspaceId}</span>
        </div>
      </div>

      <div className="grid gap-5 lg:grid-cols-[220px_minmax(0,1fr)]">
        <nav className="grid h-fit gap-1 rounded-lg border bg-background p-2 lg:sticky lg:top-6">
          {navItems.map((item) => {
            const href = item.href ? `${basePath}/${item.href}` : basePath;
            const active = pathname === href;
            const Icon = item.icon;
            return (
              <Button
                key={item.href || "dashboard"}
                asChild
                className={cn(
                  "justify-start gap-2",
                  active ? "bg-accent text-accent-foreground" : "text-muted-foreground",
                )}
                size="sm"
                variant={active ? "secondary" : "ghost"}
              >
                <Link href={href}>
                  <Icon className="h-4 w-4" />
                  {item.label}
                </Link>
              </Button>
            );
          })}
        </nav>
        <div className="min-w-0">{children}</div>
      </div>
    </section>
  );
}
