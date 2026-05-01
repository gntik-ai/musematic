"use client";

import {
  useCancelTenantDeletion,
  useReactivateTenant,
  useScheduleTenantDeletion,
  useSuspendTenant,
  useUpdateTenant,
} from "@/lib/hooks/use-admin-tenants";

export function useUpdateBranding() {
  return useUpdateTenant();
}

export {
  useCancelTenantDeletion,
  useReactivateTenant,
  useScheduleTenantDeletion,
  useSuspendTenant,
};
