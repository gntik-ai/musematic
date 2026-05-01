"use client";

import { createContext, useContext, useEffect, useMemo, useState } from "react";

export type TenantKind = "default" | "enterprise";
export type TenantStatus = "active" | "suspended" | "pending_deletion";

export interface TenantBranding {
  logo_url?: string | null;
  accent_color_hex?: string | null;
  display_name_override?: string | null;
  favicon_url?: string | null;
  support_email?: string | null;
}

export interface TenantContextValue {
  id: string;
  slug: string;
  displayName: string;
  kind: TenantKind;
  status: TenantStatus;
  branding: TenantBranding;
}

const DEFAULT_BRANDING: Required<Pick<TenantBranding, "accent_color_hex">> = {
  accent_color_hex: "#0078d4",
};

const DEFAULT_TENANT: TenantContextValue = {
  id: "00000000-0000-0000-0000-000000000001",
  slug: "default",
  displayName: "Musematic",
  kind: "default",
  status: "active",
  branding: DEFAULT_BRANDING,
};

const TenantBrandingContext = createContext<TenantContextValue>(DEFAULT_TENANT);

export function TenantBrandingProvider({
  children,
  initialTenant,
}: Readonly<{
  children: React.ReactNode;
  initialTenant?: TenantContextValue | null;
}>) {
  const [tenant, setTenant] = useState<TenantContextValue>(
    normalizeTenant(initialTenant ?? DEFAULT_TENANT),
  );

  useEffect(() => {
    let cancelled = false;
    async function loadTenant() {
      try {
        const response = await fetch("/api/v1/me/tenant", {
          credentials: "include",
          headers: { Accept: "application/json" },
        });
        if (!response.ok) {
          return;
        }
        const payload = await response.json();
        if (cancelled) {
          return;
        }
        setTenant(normalizeTenant({
          id: String(payload.id),
          slug: String(payload.slug),
          displayName: String(
            payload.branding?.display_name_override ?? payload.display_name ?? payload.slug,
          ),
          kind: payload.kind,
          status: payload.status,
          branding: {
            ...(payload.branding ?? {}),
          },
        }));
      } catch {
        return;
      }
    }
    void loadTenant();
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    const accent = tenant.branding.accent_color_hex ?? DEFAULT_BRANDING.accent_color_hex;
    document.documentElement.style.setProperty("--tenant-accent", accent);
  }, [tenant.branding.accent_color_hex]);

  const value = useMemo(() => tenant, [tenant]);
  return (
    <TenantBrandingContext.Provider value={value}>
      {children}
    </TenantBrandingContext.Provider>
  );
}

export function useTenantContext() {
  return useContext(TenantBrandingContext);
}

export function resolveTenantBranding(tenant: TenantContextValue): TenantBranding {
  return {
    ...DEFAULT_BRANDING,
    ...tenant.branding,
  };
}

function normalizeTenant(tenant: TenantContextValue): TenantContextValue {
  return {
    ...tenant,
    branding: resolveTenantBranding(tenant),
  };
}
