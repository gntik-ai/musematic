"use client";

import { AlertTriangle } from "lucide-react";
import { useTenantContext } from "@/components/features/shell/TenantBrandingProvider";
import { Button } from "@/components/ui/button";

export function SuspensionBanner() {
  const tenant = useTenantContext();

  if (tenant.status !== "suspended") {
    return null;
  }

  return (
    <div className="flex items-center justify-between gap-3 border-b bg-destructive/10 px-4 py-3 text-sm text-destructive">
      <div className="flex min-w-0 items-center gap-2">
        <AlertTriangle className="h-4 w-4 shrink-0" />
        <span className="truncate">{tenant.displayName} is suspended.</span>
      </div>
      <Button asChild size="sm" variant="outline">
        <a href={`mailto:${tenant.branding.support_email ?? "support@musematic.ai"}`}>
          Contact support
        </a>
      </Button>
    </div>
  );
}
