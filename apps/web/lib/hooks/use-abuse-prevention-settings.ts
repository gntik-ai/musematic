"use client";

/**
 * UPD-050 T028 — TanStack Query hooks for the abuse-prevention settings
 * surface. Each setting key is fetched and patched independently.
 */

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { createApiClient } from "@/lib/api";
import { useAppQuery } from "@/lib/hooks/use-api";

const adminApi = createApiClient(
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000",
);

export interface AbusePreventionSetting {
  key: string;
  value: unknown;
  updated_at: string;
  updated_by_user_id: string | null;
}

export interface AbusePreventionSettingsResponse {
  settings: AbusePreventionSetting[];
}

export const abusePreventionKeys = {
  settings: () => ["admin", "security", "abuse-prevention", "settings"] as const,
  refusals: (limit?: number, reason?: string) =>
    [
      "admin",
      "security",
      "abuse-prevention",
      "refusals",
      { limit, reason },
    ] as const,
};

export function useAbusePreventionSettings() {
  return useAppQuery<AbusePreventionSettingsResponse>(
    abusePreventionKeys.settings(),
    () =>
      adminApi.get<AbusePreventionSettingsResponse>(
        "/api/v1/admin/security/abuse-prevention/settings",
      ),
  );
}

export function useUpdateAbusePreventionSetting() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: async (input: { key: string; value: unknown }) =>
      adminApi.patch(
        `/api/v1/admin/security/abuse-prevention/settings/${input.key}`,
        { value: input.value },
      ),
    onSuccess: () =>
      client.invalidateQueries({ queryKey: abusePreventionKeys.settings() }),
  });
}

export interface RecentRefusal {
  ts: string;
  reason: string;
  dimension: string | null;
  counter_key_hash: string;
  email_domain: string | null;
  country_code: string | null;
  provider: string | null;
}

export interface RecentRefusalsResponse {
  items: RecentRefusal[];
  next_cursor: string | null;
}

export function useRecentRefusals(filter?: { limit?: number; reason?: string }) {
  const params = new URLSearchParams();
  if (filter?.limit) params.set("limit", String(filter.limit));
  if (filter?.reason) params.set("reason", filter.reason);
  const query = params.toString();
  const path = `/api/v1/admin/security/abuse-prevention/refusals/recent${query ? `?${query}` : ""}`;
  return useAppQuery<RecentRefusalsResponse>(
    abusePreventionKeys.refusals(filter?.limit, filter?.reason),
    () => adminApi.get<RecentRefusalsResponse>(path),
  );
}
