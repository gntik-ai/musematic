"use client";

import { getInitials } from "@/lib/utils";
import type { TenantAdminView } from "@/lib/hooks/use-admin-tenants";

export function TenantBrandingPreview({ tenant }: { tenant: TenantAdminView }) {
  const accent = tenant.branding.accent_color_hex ?? "#0078d4";
  const displayName = tenant.branding.display_name_override ?? tenant.display_name;

  return (
    <div className="rounded-md border p-4">
      <div className="flex items-center gap-3">
        <div
          className="flex h-12 w-12 items-center justify-center rounded-md border text-sm font-semibold"
          style={{ borderColor: accent, color: accent }}
        >
          {tenant.branding.logo_url ? (
            <img alt="" className="max-h-9 max-w-9 object-contain" src={tenant.branding.logo_url} />
          ) : (
            getInitials(displayName)
          )}
        </div>
        <div className="min-w-0">
          <p className="truncate text-sm font-semibold">{displayName}</p>
          <p className="text-xs text-muted-foreground">{tenant.subdomain}.musematic.ai</p>
        </div>
      </div>
      <div className="mt-3 h-1 rounded-full" style={{ backgroundColor: accent }} />
    </div>
  );
}
