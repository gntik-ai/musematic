"use client";

import { createApiClient } from "@/lib/api";
import { useAppMutation, useAppQuery } from "@/lib/hooks/use-api";

export type TenantKind = "default" | "enterprise";
export type TenantStatus = "active" | "suspended" | "pending_deletion";
export type TenantRegion = "global" | "eu-central" | "us-east" | "us-west";

export interface TenantBranding {
  logo_url?: string | null;
  accent_color_hex?: string | null;
  display_name_override?: string | null;
  favicon_url?: string | null;
  support_email?: string | null;
}

export interface TenantAuditEntry {
  id: string;
  event_type: string;
  actor_role?: string | null;
  created_at: string;
}

export interface TenantAdminView {
  id: string;
  slug: string;
  kind: TenantKind;
  subdomain: string;
  status: TenantStatus;
  region: TenantRegion | string;
  display_name: string;
  branding: TenantBranding;
  scheduled_deletion_at?: string | null;
  created_at: string;
  data_isolation_mode: "pool" | "silo";
  subscription_id?: string | null;
  dpa_signed_at?: string | null;
  dpa_version?: string | null;
  dpa_artifact_uri?: string | null;
  dpa_artifact_sha256?: string | null;
  contract_metadata: Record<string, unknown>;
  feature_flags: Record<string, unknown>;
  member_count: number;
  active_workspace_count: number;
  subscription_summary?: Record<string, unknown> | null;
  recent_lifecycle_audit_entries?: TenantAuditEntry[];
}

export interface TenantListResponse {
  items: TenantAdminView[];
  next_cursor: string | null;
}

export interface TenantProvisionPayload {
  slug: string;
  display_name: string;
  region: TenantRegion;
  first_admin_email: string;
  dpa_artifact_id: string;
  dpa_version: string;
  contract_metadata: Record<string, unknown>;
  branding_config: TenantBranding;
}

export interface TenantProvisionResponse {
  id: string;
  slug: string;
  subdomain: string;
  kind: TenantKind;
  status: TenantStatus;
  first_admin_invite_sent_to: string;
  dns_records_pending: boolean;
}

export interface TenantUpdatePayload {
  display_name?: string;
  region?: TenantRegion;
  branding_config?: TenantBranding;
  contract_metadata?: Record<string, unknown>;
  feature_flags?: Record<string, unknown>;
}

export interface DpaUploadResponse {
  dpa_artifact_id: string;
}

interface TenantListParams {
  kind?: TenantKind;
  status?: TenantStatus;
  q?: string;
  limit?: number;
  cursor?: string | null;
}

const adminTenantsApi = createApiClient(
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000",
);

function tenantsPath(params: TenantListParams): string {
  const query = new URLSearchParams();
  if (params.kind) {
    query.set("kind", params.kind);
  }
  if (params.status) {
    query.set("status", params.status);
  }
  if (params.q) {
    query.set("q", params.q);
  }
  if (params.cursor) {
    query.set("cursor", params.cursor);
  }
  query.set("limit", String(params.limit ?? 100));
  return `/api/v1/admin/tenants?${query.toString()}`;
}

async function listTenants(params: TenantListParams): Promise<TenantListResponse> {
  return adminTenantsApi.get<TenantListResponse>(tenantsPath(params));
}

async function getTenant(id: string): Promise<TenantAdminView> {
  return adminTenantsApi.get<TenantAdminView>(`/api/v1/admin/tenants/${id}`);
}

async function provisionTenant(
  payload: TenantProvisionPayload,
): Promise<TenantProvisionResponse> {
  return adminTenantsApi.post<TenantProvisionResponse>(
    "/api/v1/admin/tenants",
    payload,
    { skipRetry: true },
  );
}

async function uploadDpa(file: File): Promise<DpaUploadResponse> {
  const formData = new FormData();
  formData.append("file", file);
  return adminTenantsApi.post<DpaUploadResponse>(
    "/api/v1/admin/tenants/dpa-upload",
    formData,
    { skipRetry: true },
  );
}

async function updateTenant({
  id,
  payload,
}: {
  id: string;
  payload: TenantUpdatePayload;
}): Promise<TenantAdminView> {
  return adminTenantsApi.patch<TenantAdminView>(
    `/api/v1/admin/tenants/${id}`,
    payload,
    { skipRetry: true },
  );
}

export function useAdminTenants(params: TenantListParams = {}) {
  const normalizedParams = {
    ...params,
    limit: params.limit ?? 100,
  };
  return useAppQuery(
    ["admin", "tenants", normalizedParams],
    () => listTenants(normalizedParams),
  );
}

export function useAdminTenant(id: string) {
  return useAppQuery(["admin", "tenants", id], () => getTenant(id), {
    enabled: id.length > 0,
  });
}

export function useProvisionTenant() {
  return useAppMutation(provisionTenant, {
    invalidateKeys: [["admin", "tenants"]],
  });
}

export function useDpaUpload() {
  return useAppMutation(uploadDpa);
}

export function useUpdateTenant() {
  return useAppMutation(updateTenant, {
    invalidateKeys: [["admin", "tenants"]],
  });
}
