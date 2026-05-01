"use client";

import { useMemo, useState } from "react";
import { Building2 } from "lucide-react";
import { OAuthProviderAdminPanel } from "@/components/features/auth/OAuthProviderAdminPanel";
import { Select } from "@/components/ui/select";
import { useAdminTenants } from "@/lib/hooks/use-admin-tenants";
import { useTenantContext } from "@/lib/hooks/use-tenant-context";

function tenantHost(subdomain: string): string {
  if (typeof window === "undefined") {
    return subdomain;
  }
  const parts = window.location.host.split(".");
  const root = parts.length > 1 ? parts.slice(1).join(".") : window.location.host;
  return `${subdomain}.${root}`;
}

export function TenantScopedOAuthAdminPanel() {
  const tenantContext = useTenantContext();
  const tenantsQuery = useAdminTenants();
  const tenants = tenantsQuery.data?.items ?? [];
  const [selectedTenantId, setSelectedTenantId] = useState(tenantContext.id);
  const selectedTenant = useMemo(
    () => tenants.find((tenant) => tenant.id === selectedTenantId),
    [selectedTenantId, tenants],
  );

  function changeTenant(tenantId: string) {
    setSelectedTenantId(tenantId);
    const tenant = tenants.find((item) => item.id === tenantId);
    if (!tenant || tenant.id === tenantContext.id || typeof window === "undefined") {
      return;
    }
    window.location.href = `${window.location.protocol}//${tenantHost(tenant.subdomain)}${window.location.pathname}`;
  }

  return (
    <div className="space-y-5">
      <section className="rounded-md border bg-card p-4">
        <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
          <div className="flex min-w-0 items-center gap-3">
            <Building2 className="h-4 w-4 shrink-0 text-brand-accent" />
            <div className="min-w-0">
              <h2 className="text-base font-semibold tracking-normal">Tenant OAuth</h2>
              <p className="truncate text-sm text-muted-foreground">
                {selectedTenant
                  ? `Callback host: ${tenantHost(selectedTenant.subdomain)}`
                  : "Provider configuration follows the current tenant context."}
              </p>
            </div>
          </div>
          <Select
            aria-label="Tenant OAuth scope"
            className="w-full lg:w-72"
            disabled={tenantsQuery.isLoading || tenants.length === 0}
            value={selectedTenantId}
            onChange={(event) => changeTenant(event.target.value)}
          >
            {tenants.length === 0 ? (
              <option value={tenantContext.id}>{tenantContext.displayName}</option>
            ) : (
              tenants.map((tenant) => (
                <option key={tenant.id} value={tenant.id}>
                  {tenant.display_name}
                </option>
              ))
            )}
          </Select>
        </div>
      </section>
      <OAuthProviderAdminPanel />
    </div>
  );
}
