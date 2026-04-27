"use client";

import { createApiClient } from "@/lib/api";

const api = createApiClient(process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000");

export interface PreviewSource {
  origin: string;
  snippet: string;
  score: number;
  included: boolean;
  classification: string;
  reason?: string | null;
}

export interface ProfilePreviewResponse {
  sources: PreviewSource[];
  mock_response: string;
  completion_metadata: Record<string, unknown>;
  was_fallback: boolean;
}

export interface ContextProfilePayload {
  name: string;
  description?: string | null;
  source_config?: Array<Record<string, unknown>>;
  budget_config?: Record<string, unknown>;
  compaction_strategies?: string[];
  quality_weights?: Record<string, number>;
  privacy_overrides?: Record<string, unknown>;
  is_default?: boolean;
}

export interface ContextProfileResponse extends ContextProfilePayload {
  id: string;
  workspace_id: string;
  description: string | null;
  source_config: Array<Record<string, unknown>>;
  budget_config: Record<string, unknown>;
  compaction_strategies: string[];
  quality_weights: Record<string, number>;
  privacy_overrides: Record<string, unknown>;
  is_default: boolean;
  created_at: string;
  updated_at: string;
}

export interface ProfileVersion {
  id: string;
  profile_id: string;
  version_number: number;
  content_snapshot: Record<string, unknown>;
  change_summary: string | null;
  created_by: string | null;
  created_at: string;
}

export interface VersionHistoryResponse {
  versions: ProfileVersion[];
  next_cursor: string | null;
}

export interface VersionDiffResponse {
  added: Record<string, unknown>;
  removed: Record<string, unknown>;
  modified: Record<string, { old: unknown; new: unknown }>;
}

export interface ContractPreviewResponse {
  clauses_triggered: string[];
  clauses_satisfied: string[];
  clauses_violated: string[];
  final_action: "continue" | "warn" | "throttle" | "escalate" | "terminate";
  mock_response?: string | null;
  was_fallback: boolean;
}

export interface AgentContractPayload {
  agent_id: string;
  task_scope: string;
  expected_outputs?: Record<string, unknown> | null;
  quality_thresholds?: Record<string, unknown> | null;
  time_constraint_seconds?: number | null;
  cost_limit_tokens?: number | null;
  escalation_conditions?: Record<string, unknown> | null;
  success_criteria?: Record<string, unknown> | null;
  enforcement_policy?: "warn" | "throttle" | "escalate" | "terminate";
}

export interface AgentContractUpdatePayload extends Omit<AgentContractPayload, "agent_id"> {
  is_archived?: boolean;
}

export interface AgentContractResponse extends Required<AgentContractPayload> {
  id: string;
  workspace_id: string;
  is_archived: boolean;
  attached_revision_id: string | null;
  created_at: string;
  updated_at: string;
}

export interface ContractTemplate {
  id: string;
  name: string;
  description: string | null;
  category: string;
  template_content: Record<string, unknown>;
  version_number: number;
  forked_from_template_id: string | null;
  created_by_user_id: string | null;
  is_platform_authored: boolean;
  is_published: boolean;
  created_at: string;
  updated_at: string;
}

export interface ContractTemplateListResponse {
  items: ContractTemplate[];
  total: number;
}

function workspaceHeaders(workspaceId: string): HeadersInit {
  return { "X-Workspace-ID": workspaceId };
}

export function fetchProfileSchema() {
  return api.get<Record<string, unknown>>("/api/v1/context-engineering/profiles/schema");
}

export function fetchContractSchema() {
  return api.get<Record<string, unknown>>("/api/v1/trust/contracts/schema");
}

export function fetchContractSchemaEnums() {
  return api.get<{
    resource_types: string[];
    role_types: string[];
    workspace_constraints: string[];
    failure_modes: string[];
  }>("/api/v1/trust/contracts/schema-enums");
}

export function createContextProfile(workspaceId: string, payload: ContextProfilePayload) {
  return api.post<ContextProfileResponse>("/api/v1/context-engineering/profiles", payload, {
    headers: workspaceHeaders(workspaceId),
  });
}

export function updateContextProfile(
  workspaceId: string,
  profileId: string,
  payload: ContextProfilePayload,
) {
  return api.put<ContextProfileResponse>(
    `/api/v1/context-engineering/profiles/${encodeURIComponent(profileId)}`,
    payload,
    { headers: workspaceHeaders(workspaceId) },
  );
}

export function previewContextProfile(
  workspaceId: string,
  profileId: string,
  queryText: string,
) {
  return api.post<ProfilePreviewResponse>(
    `/api/v1/context-engineering/profiles/${encodeURIComponent(profileId)}/preview`,
    { query_text: queryText },
    { headers: workspaceHeaders(workspaceId) },
  );
}

export function fetchProfileVersions(
  workspaceId: string,
  profileId: string,
  cursor?: string | null,
) {
  const query = cursor ? `?cursor=${encodeURIComponent(cursor)}` : "";
  return api.get<VersionHistoryResponse>(
    `/api/v1/context-engineering/profiles/${encodeURIComponent(profileId)}/versions${query}`,
    { headers: workspaceHeaders(workspaceId) },
  );
}

export function fetchProfileVersionDiff(
  workspaceId: string,
  profileId: string,
  baseVersion: number,
  compareVersion: number,
) {
  return api.get<VersionDiffResponse>(
    `/api/v1/context-engineering/profiles/${encodeURIComponent(
      profileId,
    )}/versions/${baseVersion}/diff/${compareVersion}`,
    { headers: workspaceHeaders(workspaceId) },
  );
}

export function rollbackProfileVersion(
  workspaceId: string,
  profileId: string,
  version: number,
) {
  return api.post<ProfileVersion>(
    `/api/v1/context-engineering/profiles/${encodeURIComponent(
      profileId,
    )}/rollback/${version}`,
    undefined,
    { headers: workspaceHeaders(workspaceId) },
  );
}

export function createContract(payload: AgentContractPayload) {
  return api.post<AgentContractResponse>("/api/v1/trust/contracts", payload);
}

export function updateContract(contractId: string, payload: AgentContractUpdatePayload) {
  return api.put<AgentContractResponse>(
    `/api/v1/trust/contracts/${encodeURIComponent(contractId)}`,
    payload,
  );
}

export function previewContract(
  contractId: string,
  sampleInput: Record<string, unknown>,
  useMock = true,
  costAcknowledged = false,
) {
  return api.post<ContractPreviewResponse>(
    `/api/v1/trust/contracts/${encodeURIComponent(contractId)}/preview`,
    {
      sample_input: sampleInput,
      use_mock: useMock,
      cost_acknowledged: costAcknowledged,
    },
  );
}

export function fetchContractTemplates() {
  return api.get<ContractTemplateListResponse>("/api/v1/trust/contracts/templates");
}

export function forkContractTemplate(templateId: string, newName: string) {
  return api.post(
    `/api/v1/trust/contracts/${encodeURIComponent(templateId)}/fork`,
    { new_name: newName },
  );
}

export function attachContractToRevision(contractId: string, revisionId: string) {
  return api.post<void>(
    `/api/v1/trust/contracts/${encodeURIComponent(
      contractId,
    )}/attach-revision/${encodeURIComponent(revisionId)}`,
  );
}
