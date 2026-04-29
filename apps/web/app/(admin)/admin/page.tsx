import Link from "next/link";
import { Activity, AlertTriangle, Database, ShieldCheck, Users } from "lucide-react";
import { AdminPage } from "@/components/features/admin/AdminPage";
import { AdminTour } from "@/components/features/admin/AdminTour";
import { FirstInstallChecklist } from "@/components/features/admin/FirstInstallChecklist";
import { HelpContent } from "./help";

const summary = [
  ["Users", "1,248", "/admin/users", Users],
  ["Workspaces", "86", "/admin/workspaces", Database],
  ["Pending approvals", "4", "/admin/regions", ShieldCheck],
  ["Active incidents", "2", "/admin/incidents", AlertTriangle],
  ["Critical alerts", "7", "/admin/observability/alerts", Activity],
] as const;

export default function AdminLandingPage() {
  return (
    <AdminPage
      title="Administrator Workbench"
      description="Operational summary across the platform."
      help={<HelpContent />}
    >
      <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_360px]">
        <div className="space-y-4">
          <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-5">
            {summary.map(([label, value, href, Icon]) => (
              <Link key={label} href={href} className="rounded-md border bg-card p-4 hover:border-primary">
                <div className="flex items-center justify-between gap-2">
                  <span className="text-sm text-muted-foreground">{label}</span>
                  <Icon className="h-4 w-4 text-primary" />
                </div>
                <div className="mt-3 text-2xl font-semibold">{value}</div>
              </Link>
            ))}
          </div>
          <FirstInstallChecklist />
        </div>
        <AdminTour />
      </div>
    </AdminPage>
  );
}
