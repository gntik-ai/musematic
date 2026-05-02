"use client";

import { createApiClient } from "@/lib/api";
import { useTenantContext } from "@/lib/hooks/use-tenant-context";
import { useAppQuery } from "@/lib/hooks/use-api";

const membershipsApi = createApiClient(
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000",
);

export type MembershipTenantKind = "default" | "enterprise";

export interface MembershipEntry {
  tenant_id: string;
  tenant_slug: string;
  tenant_display_name: string;
  tenant_kind: MembershipTenantKind;
  user_id_within_tenant: string;
  role: string;
  login_url: string;
  is_current: boolean;
}

interface RawMembershipEntry extends Omit<MembershipEntry, "is_current"> {
  is_current_tenant: boolean;
}

interface RawMembershipsListResponse {
  memberships: RawMembershipEntry[];
  count: number;
}

export interface MembershipsListResponse {
  memberships: MembershipEntry[];
  count: number;
}

export const membershipsQueryKeys = {
  list: ["me", "memberships"] as const,
};

export function useMemberships() {
  const tenant = useTenantContext();
  const query = useAppQuery(membershipsQueryKeys.list, listMemberships);
  const memberships = query.data?.memberships ?? [];
  const currentMembership =
    memberships.find((membership) => membership.is_current) ??
    memberships.find((membership) => membership.tenant_id === tenant.id) ??
    null;

  return {
    ...query,
    count: query.data?.count ?? memberships.length,
    currentMembership,
    memberships,
  };
}

async function listMemberships(): Promise<MembershipsListResponse> {
  const response = await membershipsApi.get<RawMembershipsListResponse>(
    "/api/v1/me/memberships",
  );
  return {
    count: response.count,
    memberships: response.memberships.map((membership) => ({
      ...membership,
      is_current: membership.is_current_tenant,
    })),
  };
}
