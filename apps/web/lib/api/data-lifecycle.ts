"use client";

import { createApiClient } from "@/lib/api";

export interface ExportJob {
  id: string;
  scope_type: "workspace" | "tenant";
  scope_id: string;
  status: "pending" | "processing" | "completed" | "failed";
  requested_at: string;
  started_at?: string | null;
  completed_at?: string | null;
  output_size_bytes?: number | null;
  output_expires_at?: string | null;
  output_url?: string | null;
  error_message?: string | null;
}

export interface DeletionJob {
  id: string;
  scope_type: "workspace" | "tenant";
  scope_id: string;
  phase: "phase_1" | "phase_2" | "completed" | "aborted";
  grace_period_days: number;
  grace_ends_at: string;
  cascade_started_at?: string | null;
  cascade_completed_at?: string | null;
  tombstone_id?: string | null;
  final_export_job_id?: string | null;
  abort_reason?: string | null;
}

export interface SubProcessor {
  id: string;
  name: string;
  category: string;
  location: string;
  data_categories: string[];
  privacy_policy_url?: string | null;
  dpa_url?: string | null;
  is_active: boolean;
  started_using_at?: string | null;
  notes?: string | null;
  updated_at: string;
}

export interface DPAActive {
  version: string;
  signed_at: string;
  sha256: string;
  vault_path?: string;
}

const api = createApiClient(process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000");

// ============================================================================
// Workspace export
// ============================================================================

export async function requestWorkspaceExport(workspaceId: string): Promise<ExportJob> {
  const res = await api.post(`/api/v1/workspaces/${workspaceId}/data-export`, {});
  return res as ExportJob;
}

export async function listWorkspaceExportJobs(
  workspaceId: string,
  params?: { limit?: number; status?: string },
): Promise<{ items: ExportJob[]; next_cursor: string | null }> {
  const qs = new URLSearchParams();
  if (params?.limit) qs.set("limit", String(params.limit));
  if (params?.status) qs.set("status", params.status);
  const url = `/api/v1/workspaces/${workspaceId}/data-export/jobs${qs.toString() ? `?${qs}` : ""}`;
  return api.get(url) as Promise<{ items: ExportJob[]; next_cursor: string | null }>;
}

export async function getWorkspaceExportJob(
  workspaceId: string,
  jobId: string,
): Promise<ExportJob> {
  return api.get(
    `/api/v1/workspaces/${workspaceId}/data-export/jobs/${jobId}`,
  ) as Promise<ExportJob>;
}

// ============================================================================
// Workspace deletion
// ============================================================================

export interface DeletionRequest {
  typed_confirmation: string;
  reason?: string;
}

export async function requestWorkspaceDeletion(
  workspaceId: string,
  body: DeletionRequest,
): Promise<DeletionJob> {
  return api.post(
    `/api/v1/workspaces/${workspaceId}/deletion-jobs`,
    body,
  ) as Promise<DeletionJob>;
}

export async function getWorkspaceDeletionJob(
  workspaceId: string,
  jobId: string,
): Promise<DeletionJob> {
  return api.get(
    `/api/v1/workspaces/${workspaceId}/deletion-jobs/${jobId}`,
  ) as Promise<DeletionJob>;
}

export async function cancelWorkspaceDeletion(
  token: string,
): Promise<{ message: string }> {
  return api.post(
    `/api/v1/workspaces/cancel-deletion/${token}`,
    {},
  ) as Promise<{ message: string }>;
}

// ============================================================================
// Tenant export + deletion (super-admin only)
// ============================================================================

export async function requestTenantExport(tenantId: string): Promise<ExportJob> {
  return api.post(
    `/api/v1/admin/tenants/${tenantId}/data-export`,
    { include_workspaces: true, include_users: true, include_audit_chain: true },
  ) as Promise<ExportJob>;
}

export interface TenantDeletionRequest {
  typed_confirmation: string;
  reason: string;
  include_final_export: boolean;
  grace_period_days: number;
}

export async function requestTenantDeletion(
  tenantId: string,
  body: TenantDeletionRequest,
  twoPaToken: string,
): Promise<DeletionJob> {
  return api.post(
    `/api/v1/admin/tenants/${tenantId}/deletion-jobs`,
    body,
    { headers: { "X-2PA-Token": twoPaToken } },
  ) as Promise<DeletionJob>;
}

export async function getTenantDeletionJob(
  tenantId: string,
  jobId: string,
): Promise<DeletionJob> {
  return api.get(
    `/api/v1/admin/tenants/${tenantId}/deletion-jobs/${jobId}`,
  ) as Promise<DeletionJob>;
}

// ============================================================================
// Sub-processors (admin)
// ============================================================================

export async function listSubProcessorsAdmin(): Promise<SubProcessor[]> {
  return api.get(`/api/v1/admin/sub-processors`) as Promise<SubProcessor[]>;
}

export interface SubProcessorCreate {
  name: string;
  category: string;
  location: string;
  data_categories: string[];
  privacy_policy_url?: string;
  dpa_url?: string;
  started_using_at?: string;
  notes?: string;
}

export async function addSubProcessor(body: SubProcessorCreate): Promise<SubProcessor> {
  return api.post(`/api/v1/admin/sub-processors`, body) as Promise<SubProcessor>;
}

export async function updateSubProcessor(
  id: string,
  body: Partial<SubProcessorCreate> & { is_active?: boolean },
): Promise<SubProcessor> {
  return api.patch(
    `/api/v1/admin/sub-processors/${id}`,
    body,
  ) as Promise<SubProcessor>;
}

export async function deleteSubProcessor(id: string): Promise<SubProcessor> {
  return api.delete(`/api/v1/admin/sub-processors/${id}`) as Promise<SubProcessor>;
}

// ============================================================================
// DPA (admin)
// ============================================================================

export async function uploadDPA(
  tenantId: string,
  file: File,
  version: string,
  effective_date: string,
): Promise<{ tenant_id: string; version: string; sha256: string }> {
  const fd = new FormData();
  fd.append("file", file);
  fd.append("version", version);
  fd.append("effective_date", effective_date);
  // Use fetch directly so the browser sets the multipart Content-Type.
  const baseUrl = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
  const res = await fetch(`${baseUrl}/api/v1/admin/tenants/${tenantId}/dpa`, {
    method: "POST",
    body: fd,
    credentials: "include",
  });
  if (!res.ok) {
    throw new Error(`DPA upload failed: ${res.status}`);
  }
  return (await res.json()) as { tenant_id: string; version: string; sha256: string };
}

export async function getDPAMetadata(
  tenantId: string,
): Promise<{ active: DPAActive | null; history: unknown[] }> {
  return api.get(`/api/v1/admin/tenants/${tenantId}/dpa`) as Promise<{
    active: DPAActive | null;
    history: unknown[];
  }>;
}

// ============================================================================
// Article 28 evidence
// ============================================================================

export async function generateArticle28Evidence(
  tenantId: string,
): Promise<{ job_id: string; status: string }> {
  return api.post(
    `/api/v1/admin/tenants/${tenantId}/article28-evidence`,
    {},
  ) as Promise<{ job_id: string; status: string }>;
}
