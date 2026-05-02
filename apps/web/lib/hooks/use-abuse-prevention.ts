"use client";

/**
 * UPD-050 — TanStack Query hooks for the abuse-prevention admin surface.
 *
 * Endpoints under `/api/v1/admin/security/*` per
 * `specs/100-abuse-prevention/contracts/admin-security-rest.md`.
 */

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { createApiClient } from "@/lib/api";
import { useAppQuery } from "@/lib/hooks/use-api";

// TODO(UPD-050): replace inline stubs with imports from `@/lib/security/types`
// once the abuse-prevention spec is created and the shared type module exists.
// See specs/071-e2e-kind-testing/NOTES.md follow-up F2.
type AbusePreventionSettings = Record<string, unknown>;
interface EmailOverride {
  domain: string;
  policy: string;
}
interface EmailOverrideAdd {
  domain: string;
  policy: string;
  reason?: string;
}
interface GeoPolicyView {
  mode: string;
  country_codes: string[];
}
interface GeoPolicyUpdate {
  mode?: string;
  country_codes?: string[];
}
interface TrustedAllowlistEntry {
  id: string;
  cidr: string;
  description?: string;
}
interface TrustedAllowlistAdd {
  cidr: string;
  description?: string;
}

const adminApi = createApiClient(
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000",
);

export const abuseKeys = {
  settings: () => ["admin", "security", "settings"] as const,
  emailOverrides: () => ["admin", "security", "email-overrides"] as const,
  trustedAllowlist: () => ["admin", "security", "trusted-allowlist"] as const,
  geoPolicy: () => ["admin", "security", "geo-policy"] as const,
};

// --- Settings -------------------------------------------------------------

export function useAbuseSettings() {
  return useAppQuery<AbusePreventionSettings>(
    abuseKeys.settings(),
    () =>
      adminApi.get<AbusePreventionSettings>(
        "/api/v1/admin/security/abuse-prevention/settings",
      ),
  );
}

export function useUpdateSetting() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: async (input: { key: string; value: unknown }) =>
      adminApi.patch(
        `/api/v1/admin/security/abuse-prevention/settings/${input.key}`,
        { value: input.value },
      ),
    onSuccess: () => {
      client.invalidateQueries({ queryKey: abuseKeys.settings() });
    },
  });
}

// --- Email overrides ------------------------------------------------------

interface EmailOverrideListResponse {
  items: EmailOverride[];
}

export function useEmailOverrides() {
  return useAppQuery<EmailOverrideListResponse>(
    abuseKeys.emailOverrides(),
    () =>
      adminApi.get<EmailOverrideListResponse>(
        "/api/v1/admin/security/email-overrides",
      ),
  );
}

export function useAddEmailOverride() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: async (body: EmailOverrideAdd) =>
      adminApi.post(`/api/v1/admin/security/email-overrides`, body),
    onSuccess: () => {
      client.invalidateQueries({ queryKey: abuseKeys.emailOverrides() });
    },
  });
}

export function useRemoveEmailOverride() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: async (domain: string) =>
      adminApi.delete(
        `/api/v1/admin/security/email-overrides/${encodeURIComponent(domain)}`,
      ),
    onSuccess: () => {
      client.invalidateQueries({ queryKey: abuseKeys.emailOverrides() });
    },
  });
}

// --- Trusted allowlist ----------------------------------------------------

interface TrustedAllowlistListResponse {
  items: TrustedAllowlistEntry[];
}

export function useTrustedAllowlist() {
  return useAppQuery<TrustedAllowlistListResponse>(
    abuseKeys.trustedAllowlist(),
    () =>
      adminApi.get<TrustedAllowlistListResponse>(
        "/api/v1/admin/security/trusted-allowlist",
      ),
  );
}

export function useAddTrustedAllowlist() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: async (body: TrustedAllowlistAdd) =>
      adminApi.post(`/api/v1/admin/security/trusted-allowlist`, body),
    onSuccess: () => {
      client.invalidateQueries({ queryKey: abuseKeys.trustedAllowlist() });
    },
  });
}

export function useRemoveTrustedAllowlist() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: async (id: string) =>
      adminApi.delete(`/api/v1/admin/security/trusted-allowlist/${id}`),
    onSuccess: () => {
      client.invalidateQueries({ queryKey: abuseKeys.trustedAllowlist() });
    },
  });
}

// --- Geo policy -----------------------------------------------------------

export function useGeoPolicy() {
  return useAppQuery<GeoPolicyView>(
    abuseKeys.geoPolicy(),
    () => adminApi.get<GeoPolicyView>("/api/v1/admin/security/geo-policy"),
  );
}

export function useUpdateGeoPolicy() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: async (body: GeoPolicyUpdate) =>
      adminApi.patch(`/api/v1/admin/security/geo-policy`, body),
    onSuccess: () => {
      client.invalidateQueries({ queryKey: abuseKeys.geoPolicy() });
    },
  });
}
