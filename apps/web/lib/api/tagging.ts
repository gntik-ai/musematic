"use client";

import { createApiClient } from "@/lib/api";
import { useAppMutation, useAppQuery } from "@/lib/hooks/use-api";

export type TaggableEntityType =
  | "workspace"
  | "agent"
  | "fleet"
  | "workflow"
  | "policy"
  | "certification"
  | "evaluation_run";

export interface TagResponse {
  tag: string;
  created_by: string | null;
  created_at: string;
}

export interface EntityTagsResponse {
  entity_type: TaggableEntityType;
  entity_id: string;
  tags: TagResponse[];
}

export interface LabelResponse {
  key: string;
  value: string;
  created_by: string | null;
  created_at: string;
  updated_at: string;
  is_reserved: boolean;
}

export interface EntityLabelsResponse {
  entity_type: TaggableEntityType;
  entity_id: string;
  labels: LabelResponse[];
}

export interface CrossEntityTagSearchResponse {
  tag: string;
  entities: Partial<Record<TaggableEntityType, string[]>>;
  next_cursor: string | null;
}

export interface SavedViewResponse {
  id: string;
  owner_id: string;
  workspace_id: string | null;
  name: string;
  entity_type: TaggableEntityType;
  filters: Record<string, unknown>;
  is_owner: boolean;
  is_shared: boolean;
  is_orphan_transferred: boolean;
  is_orphan: boolean;
  version: number;
  created_at: string;
  updated_at: string;
}

export interface SavedViewCreateRequest {
  workspace_id: string | null;
  name: string;
  entity_type: TaggableEntityType;
  filters: Record<string, unknown>;
  shared: boolean;
}

export interface SavedViewUpdateRequest {
  expected_version: number;
  name?: string;
  filters?: Record<string, unknown>;
  shared?: boolean;
}

export interface LabelExpressionValidationResponse {
  valid: boolean;
  error: {
    line: number;
    col: number;
    token: string;
    message: string;
  } | null;
}

const taggingApi = createApiClient(process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000");

export const taggingQueryKeys = {
  entityTags: (entityType: string, entityId: string) =>
    ["tagging", "tags", entityType, entityId] as const,
  entityLabels: (entityType: string, entityId: string) =>
    ["tagging", "labels", entityType, entityId] as const,
  crossEntityTag: (tag: string, entityTypes?: string[]) =>
    ["tagging", "search", tag, entityTypes?.join(",") ?? "all"] as const,
  savedViews: (entityType: string, workspaceId?: string | null) =>
    ["tagging", "saved-views", entityType, workspaceId ?? "none"] as const,
  labelExpression: (expression: string) => ["tagging", "label-expression", expression] as const,
};

function query(values: Record<string, string | number | undefined | null>): string {
  const searchParams = new URLSearchParams();
  Object.entries(values).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== "") {
      searchParams.set(key, String(value));
    }
  });
  const rendered = searchParams.toString();
  return rendered ? `?${rendered}` : "";
}

export function fetchEntityTags(entityType: TaggableEntityType, entityId: string) {
  return taggingApi.get<EntityTagsResponse>(
    `/api/v1/tags/${entityType}/${encodeURIComponent(entityId)}`,
  );
}

export function attachTag(entityType: TaggableEntityType, entityId: string, tag: string) {
  return taggingApi.post<TagResponse>(
    `/api/v1/tags/${entityType}/${encodeURIComponent(entityId)}`,
    { tag },
  );
}

export function detachTag(entityType: TaggableEntityType, entityId: string, tag: string) {
  return taggingApi.delete<void>(
    `/api/v1/tags/${entityType}/${encodeURIComponent(entityId)}/${encodeURIComponent(tag)}`,
  );
}

export function fetchEntityLabels(entityType: TaggableEntityType, entityId: string) {
  return taggingApi.get<EntityLabelsResponse>(
    `/api/v1/labels/${entityType}/${encodeURIComponent(entityId)}`,
  );
}

export function upsertLabel(
  entityType: TaggableEntityType,
  entityId: string,
  key: string,
  value: string,
) {
  return taggingApi.post<LabelResponse>(
    `/api/v1/labels/${entityType}/${encodeURIComponent(entityId)}`,
    { key, value },
  );
}

export function upsertReservedLabel(
  entityType: TaggableEntityType,
  entityId: string,
  key: string,
  value: string,
) {
  return taggingApi.post<LabelResponse>(
    `/api/v1/admin/labels/reserved/${entityType}/${encodeURIComponent(entityId)}`,
    { key, value },
  );
}

export function detachLabel(entityType: TaggableEntityType, entityId: string, key: string) {
  return taggingApi.delete<void>(
    `/api/v1/labels/${entityType}/${encodeURIComponent(entityId)}/${encodeURIComponent(key)}`,
  );
}

export function searchByTag(tag: string, entityTypes?: TaggableEntityType[], cursor?: string | null) {
  return taggingApi.get<CrossEntityTagSearchResponse>(
    `/api/v1/tags/${encodeURIComponent(tag)}/entities${query({
      entity_types: entityTypes?.join(","),
      cursor,
    })}`,
  );
}

export function fetchSavedViews(entityType: TaggableEntityType, workspaceId?: string | null) {
  return taggingApi.get<SavedViewResponse[]>(
    `/api/v1/saved-views${query({ entity_type: entityType, workspace_id: workspaceId })}`,
  );
}

export function createSavedView(payload: SavedViewCreateRequest) {
  return taggingApi.post<SavedViewResponse>("/api/v1/saved-views", payload);
}

export function updateSavedView(id: string, payload: SavedViewUpdateRequest) {
  return taggingApi.patch<SavedViewResponse>(`/api/v1/saved-views/${id}`, payload);
}

export function shareSavedView(id: string) {
  return taggingApi.post<SavedViewResponse>(`/api/v1/saved-views/${id}/share`, {});
}

export function unshareSavedView(id: string) {
  return taggingApi.post<SavedViewResponse>(`/api/v1/saved-views/${id}/unshare`, {});
}

export function deleteSavedView(id: string) {
  return taggingApi.delete<void>(`/api/v1/saved-views/${id}`);
}

export function validateLabelExpression(expression: string) {
  return taggingApi.post<LabelExpressionValidationResponse>("/api/v1/labels/expression/validate", {
    expression,
  });
}

export function useEntityTags(entityType: TaggableEntityType, entityId: string, enabled = true) {
  return useAppQuery(
    taggingQueryKeys.entityTags(entityType, entityId),
    () => fetchEntityTags(entityType, entityId),
    { enabled: enabled && Boolean(entityId) },
  );
}

export function useEntityLabels(entityType: TaggableEntityType, entityId: string, enabled = true) {
  return useAppQuery(
    taggingQueryKeys.entityLabels(entityType, entityId),
    () => fetchEntityLabels(entityType, entityId),
    { enabled: enabled && Boolean(entityId) },
  );
}

export function useCrossEntityTagSearch(tag: string, entityTypes?: TaggableEntityType[]) {
  return useAppQuery(
    taggingQueryKeys.crossEntityTag(tag, entityTypes),
    () => searchByTag(tag, entityTypes),
    { enabled: tag.trim().length > 0 },
  );
}

export function useSavedViews(entityType: TaggableEntityType, workspaceId?: string | null) {
  return useAppQuery(taggingQueryKeys.savedViews(entityType, workspaceId), () =>
    fetchSavedViews(entityType, workspaceId),
  );
}

export function useTagAttach(entityType: TaggableEntityType, entityId: string) {
  return useAppMutation((tag: string) => attachTag(entityType, entityId, tag), {
    invalidateKeys: [taggingQueryKeys.entityTags(entityType, entityId)],
  });
}

export function useTagDetach(entityType: TaggableEntityType, entityId: string) {
  return useAppMutation((tag: string) => detachTag(entityType, entityId, tag), {
    invalidateKeys: [taggingQueryKeys.entityTags(entityType, entityId)],
  });
}

export function useLabelUpsert(entityType: TaggableEntityType, entityId: string) {
  return useAppMutation(
    (payload: { key: string; value: string }) =>
      upsertLabel(entityType, entityId, payload.key, payload.value),
    { invalidateKeys: [taggingQueryKeys.entityLabels(entityType, entityId)] },
  );
}

export function useLabelDetach(entityType: TaggableEntityType, entityId: string) {
  return useAppMutation((key: string) => detachLabel(entityType, entityId, key), {
    invalidateKeys: [taggingQueryKeys.entityLabels(entityType, entityId)],
  });
}

export function useSavedViewCreate(entityType: TaggableEntityType, workspaceId?: string | null) {
  return useAppMutation(createSavedView, {
    invalidateKeys: [taggingQueryKeys.savedViews(entityType, workspaceId)],
  });
}

export function useSavedViewShare(entityType: TaggableEntityType, workspaceId?: string | null) {
  return useAppMutation(
    ({ id, shared }: { id: string; shared: boolean }) =>
      shared ? shareSavedView(id) : unshareSavedView(id),
    { invalidateKeys: [taggingQueryKeys.savedViews(entityType, workspaceId)] },
  );
}

export function useLabelExpressionValidate(expression: string) {
  return useAppQuery(
    taggingQueryKeys.labelExpression(expression),
    () => validateLabelExpression(expression),
    { enabled: expression.trim().length > 0 },
  );
}
