"use client";

import Link from "next/link";
import { CheckCircle2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { useUpdateChecklistState } from "@/lib/hooks/use-admin-mutations";
import { useAdminStore } from "@/lib/stores/admin-store";

const items = [
  { id: "instance", label: "Verify instance settings", href: "/admin/settings" },
  { id: "oauth", label: "Configure OAuth providers", href: "/admin/oauth-providers" },
  { id: "admins", label: "Invite other admins", href: "/admin/users" },
  { id: "health", label: "Check platform health", href: "/admin/health" },
  {
    id: "observability",
    label: "Install observability stack",
    href: "/admin/observability/dashboards",
  },
  { id: "backup", label: "Run first backup", href: "/admin/lifecycle/backup" },
  { id: "audit", label: "Review audit chain", href: "/admin/audit-chain" },
  { id: "security", label: "Review security settings", href: "/admin/security/rotations" },
  { id: "mfa", label: "Enroll MFA", href: "/admin/sessions" },
] as const;

export function FirstInstallChecklist() {
  const dismissed = useAdminStore((state) => state.firstInstallChecklistDismissed);
  const dismissChecklist = useAdminStore((state) => state.dismissChecklist);
  const updateChecklist = useUpdateChecklistState();

  if (dismissed) {
    return null;
  }

  return (
    <div className="rounded-md border bg-card p-4">
      <div className="mb-3 flex items-center justify-between gap-3">
        <div className="flex items-center gap-2 font-medium">
          <CheckCircle2 className="h-4 w-4 text-primary" />
          First install checklist
        </div>
        <Button variant="ghost" size="sm" onClick={dismissChecklist}>
          Hide
        </Button>
      </div>
      <div className="grid gap-2 md:grid-cols-2">
        {items.map(({ id, label, href }) => (
          <label key={id} className="flex items-center gap-3 rounded-md border px-3 py-2 text-sm">
            <Checkbox
              onChange={(event) =>
                updateChecklist.mutate({ state: { [id]: event.target.checked } })
              }
            />
            <Link href={href} className="hover:text-primary">
              {label}
            </Link>
          </label>
        ))}
      </div>
    </div>
  );
}
