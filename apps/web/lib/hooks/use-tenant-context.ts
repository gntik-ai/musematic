"use client";

import {
  resolveTenantBranding,
  useTenantContext,
} from "@/components/features/shell/TenantBrandingProvider";

export { useTenantContext };

export function useTenantBranding() {
  return resolveTenantBranding(useTenantContext());
}
