"use client";

import Link from "next/link";
import { CheckCircle2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { useUpdateChecklistState } from "@/lib/hooks/use-admin-mutations";
import { useAdminStore } from "@/lib/stores/admin-store";

const items = [
  ["instance", "Verify instance settings", "/admin/settings"],
  ["oauth", "Configure OAuth providers", "/admin/oauth-providers"],
  ["admins", "Invite other admins", "/admin/users"],
  ["observability", "Install observability stack", "/admin/observability/dashboards"],
  ["backup", "Run first backup", "/admin/lifecycle/backup"],
  ["security", "Review security settings", "/admin/security/rotations"],
  ["mfa", "Enroll MFA", "/admin/sessions"],
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
        {items.map(([id, label, href]) => (
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
