"use client";

import { createApiClient } from "@/lib/api";
import { useAppMutation } from "@/lib/hooks/use-api";

type AdminMutationPayload = Record<string, unknown> | undefined;

interface AdminActionResponse {
  action: string;
  resource: string;
  accepted: boolean;
  preview: boolean;
  affected_count: number;
  bulk_action_id?: string | null;
  message?: string | null;
}

interface ImpersonationStartResponse {
  session: {
    session_id: string;
    impersonating_user_id: string;
    effective_user_id: string;
    expires_at: string;
  };
  access_token: string;
}

const adminApi = createApiClient(process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000");

function postAction(path: string, payload?: AdminMutationPayload) {
  return adminApi.post<AdminActionResponse>(path, payload);
}

function patchAction(path: string, payload?: AdminMutationPayload) {
  return adminApi.patch<AdminActionResponse>(path, payload);
}

function putAction(path: string, payload?: AdminMutationPayload) {
  return adminApi.put<AdminActionResponse>(path, payload);
}

function deleteAction(path: string) {
  return adminApi.delete<AdminActionResponse>(path);
}

export function useAdminPostAction(path: string, invalidateKeys: string[][] = []) {
  return useAppMutation((payload: AdminMutationPayload) => postAction(path, payload), {
    invalidateKeys,
  });
}

export function useAdminPatchAction(path: string, invalidateKeys: string[][] = []) {
  return useAppMutation((payload: AdminMutationPayload) => patchAction(path, payload), {
    invalidateKeys,
  });
}

export function useAdminPutAction(path: string, invalidateKeys: string[][] = []) {
  return useAppMutation((payload: AdminMutationPayload) => putAction(path, payload), {
    invalidateKeys,
  });
}

export function useAdminDeleteAction(path: string, invalidateKeys: string[][] = []) {
  return useAppMutation(() => deleteAction(path), {
    invalidateKeys,
  });
}

export function useToggleReadOnlyMode() {
  return useAdminPatchAction("/api/v1/admin/sessions/me/read-only-mode", [
    ["admin", "session"],
  ]);
}

export function useStartImpersonation() {
  return useAppMutation(
    (payload: { target_user_id: string; justification: string }) =>
      adminApi.post<ImpersonationStartResponse>("/api/v1/admin/impersonation/start", payload),
    {
      invalidateKeys: [["admin", "impersonation"]],
    },
  );
}

export function useEndImpersonation() {
  return useAdminPostAction("/api/v1/admin/impersonation/end", [["admin", "impersonation"]]);
}

export function useCreateTwoPersonAuthRequest() {
  return useAdminPostAction("/api/v1/admin/2pa/requests", [["admin", "2pa"]]);
}

export function useApproveTwoPersonAuthRequest(requestId: string) {
  return useAdminPostAction(`/api/v1/admin/2pa/requests/${requestId}/approve`, [
    ["admin", "2pa"],
  ]);
}

export function useRejectTwoPersonAuthRequest(requestId: string) {
  return useAdminPostAction(`/api/v1/admin/2pa/requests/${requestId}/reject`, [
    ["admin", "2pa"],
  ]);
}

export function useUpdateChecklistState() {
  return useAdminPatchAction("/api/v1/admin/users/me/checklist-state", [
    ["admin", "checklist"],
  ]);
}

export function useSuspendUser(userId: string) {
  return useAdminPostAction(`/api/v1/admin/users/${userId}/suspend`, [["admin", "users"]]);
}

export function useReactivateUser(userId: string) {
  return useAdminPostAction(`/api/v1/admin/users/${userId}/reactivate`, [["admin", "users"]]);
}

export function useForceUserMfaEnrollment(userId: string) {
  return useAdminPostAction(`/api/v1/admin/users/${userId}/force-mfa-enrollment`, [
    ["admin", "users"],
  ]);
}

export function useForceUserPasswordReset(userId: string) {
  return useAdminPostAction(`/api/v1/admin/users/${userId}/force-password-reset`, [
    ["admin", "users"],
  ]);
}

export function useDeleteUser(userId: string) {
  return useAdminDeleteAction(`/api/v1/admin/users/${userId}`, [["admin", "users"]]);
}

export function useBulkSuspendUsers(preview = false) {
  return useAdminPostAction(`/api/v1/admin/users/bulk/suspend?preview=${String(preview)}`, [
    ["admin", "users"],
    ["admin", "activity"],
  ]);
}

export function useUpdateRolePermissions(roleId: string) {
  return useAdminPutAction(`/api/v1/admin/roles/${roleId}/permissions`, [["admin", "roles"]]);
}

export function useCloneRole(roleId: string) {
  return useAdminPostAction(`/api/v1/admin/roles/${roleId}/clone`, [["admin", "roles"]]);
}

export function useAssignRole(roleId: string) {
  return useAdminPostAction(`/api/v1/admin/roles/${roleId}/assign`, [["admin", "roles"]]);
}

export function useMapGroupToRole(groupId: string) {
  return useAdminPostAction(`/api/v1/admin/groups/${groupId}/role-mappings`, [
    ["admin", "groups"],
  ]);
}

export function useRevokeSession(sessionId: string) {
  return useAdminDeleteAction(`/api/v1/admin/sessions/${sessionId}`, [["admin", "sessions"]]);
}

export function useBulkRevokeSessions() {
  return useAdminPostAction("/api/v1/admin/sessions/bulk-revoke", [["admin", "sessions"]]);
}

export function useCreateOAuthProvider() {
  return useAdminPostAction("/api/v1/admin/oauth-providers", [["admin", "oauth-providers"]]);
}

export function useUpdateOAuthProvider(providerId: string) {
  return useAdminPutAction(`/api/v1/admin/oauth-providers/${providerId}`, [
    ["admin", "oauth-providers"],
  ]);
}

export function useDeleteOAuthProvider(providerId: string) {
  return useAdminDeleteAction(`/api/v1/admin/oauth-providers/${providerId}`, [
    ["admin", "oauth-providers"],
  ]);
}

export function useSyncIborConnector(connectorId: string) {
  return useAdminPostAction(`/api/v1/admin/ibor/connectors/${connectorId}/sync`, [
    ["admin", "ibor"],
  ]);
}

export function useRotateApiKey(keyId: string) {
  return useAdminPostAction(`/api/v1/admin/api-keys/${keyId}/rotate`, [["admin", "api-keys"]]);
}

export function useRevokeApiKey(keyId: string) {
  return useAdminDeleteAction(`/api/v1/admin/api-keys/${keyId}`, [["admin", "api-keys"]]);
}

export function useCreateTenant() {
  return useAdminPostAction("/api/v1/admin/tenants", [["admin", "tenants"]]);
}

export function useUpdateTenant(tenantId: string) {
  return useAdminPatchAction(`/api/v1/admin/tenants/${tenantId}`, [["admin", "tenants"]]);
}

export function useUpdateWorkspaceQuotas(workspaceId: string) {
  return useAdminPatchAction(`/api/v1/admin/workspaces/${workspaceId}/quotas`, [
    ["admin", "workspaces"],
  ]);
}

export function useUpdatePlatformSettings() {
  return useAdminPutAction("/api/v1/admin/settings", [["admin", "settings"]]);
}

export function useUpdateFeatureFlag(key: string) {
  return useAdminPutAction(`/api/v1/admin/feature-flags/${key}`, [
    ["admin", "feature-flags"],
  ]);
}

export function useDeleteFeatureFlagOverride(key: string) {
  return useAdminDeleteAction(`/api/v1/admin/feature-flags/${key}`, [
    ["admin", "feature-flags"],
  ]);
}

export function useCreateConnector() {
  return useAdminPostAction("/api/v1/admin/connectors", [["admin", "connectors"]]);
}

export function useRotateConnectorSecret(connectorId: string) {
  return useAdminPostAction(`/api/v1/admin/connectors/${connectorId}/rotate-secret`, [
    ["admin", "connectors"],
  ]);
}

export function useScheduleMaintenanceWindow() {
  return useAdminPostAction("/api/v1/admin/maintenance", [["admin", "maintenance"]]);
}

export function useExecuteFailover() {
  return useAppMutation(
    (
      payload: (Record<string, unknown> & { twoPersonAuthToken?: string }) | undefined,
    ) => {
      const { twoPersonAuthToken, ...body } = payload ?? {};
      return adminApi.post<AdminActionResponse>(
        "/api/v1/admin/regions/failover/execute",
        body,
        twoPersonAuthToken
          ? { headers: { "X-Two-Person-Auth-Token": twoPersonAuthToken } }
          : undefined,
      );
    },
    {
      invalidateKeys: [
        ["admin", "regions"],
        ["admin", "health"],
      ],
    },
  );
}

export function useCreateRunbook() {
  return useAdminPostAction("/api/v1/admin/runbooks", [["admin", "runbooks"]]);
}

export function useCreateIncidentIntegration() {
  return useAdminPostAction("/api/v1/admin/integrations/incidents", [
    ["admin", "integrations"],
  ]);
}

export function useCreateNotificationIntegration() {
  return useAdminPostAction("/api/v1/admin/integrations/notifications", [
    ["admin", "integrations"],
  ]);
}

export function useCreateWebhookIntegration() {
  return useAdminPostAction("/api/v1/admin/integrations/webhooks", [
    ["admin", "integrations"],
  ]);
}

export function useApplyConfigurationImport() {
  return useAdminPostAction("/api/v1/admin/config/import/apply", [
    ["admin", "settings"],
    ["admin", "activity"],
  ]);
}
