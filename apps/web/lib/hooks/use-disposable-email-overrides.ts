"use client";

/**
 * UPD-050 T043 — TanStack Query hooks for the disposable-email override
 * list at /api/v1/admin/security/email-overrides/*.
 */

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { createApiClient } from "@/lib/api";
import { useAppQuery } from "@/lib/hooks/use-api";

const adminApi = createApiClient(
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000",
);

export interface DisposableEmailOverride {
  domain: string;
  mode: "allow" | "block";
  reason: string | null;
  created_at: string;
  created_by_user_id: string | null;
}

export interface DisposableEmailOverridesResponse {
  items: DisposableEmailOverride[];
}

export const overrideKeys = {
  list: () => ["admin", "security", "email-overrides"] as const,
};

export function useDisposableEmailOverrides() {
  return useAppQuery<DisposableEmailOverridesResponse>(
    overrideKeys.list(),
    () =>
      adminApi.get<DisposableEmailOverridesResponse>(
        "/api/v1/admin/security/email-overrides",
      ),
  );
}

export function useAddDisposableEmailOverride() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: async (input: {
      domain: string;
      mode: "allow" | "block";
      reason?: string | undefined;
    }) => adminApi.post("/api/v1/admin/security/email-overrides", input),
    onSuccess: () => client.invalidateQueries({ queryKey: overrideKeys.list() }),
  });
}

export function useRemoveDisposableEmailOverride() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: async (domain: string) =>
      adminApi.delete(
        `/api/v1/admin/security/email-overrides/${encodeURIComponent(domain)}`,
      ),
    onSuccess: () => client.invalidateQueries({ queryKey: overrideKeys.list() }),
  });
}

export function useRefreshBlocklist() {
  return useMutation({
    mutationFn: async () =>
      adminApi.post(
        "/api/v1/admin/security/email-overrides/refresh-blocklist",
        {},
      ),
  });
}
