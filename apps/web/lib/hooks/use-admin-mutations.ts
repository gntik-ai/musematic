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
  message?: string | null;
}

const adminApi = createApiClient(process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000");

function postAction(path: string, payload?: AdminMutationPayload) {
  return adminApi.post<AdminActionResponse>(path, payload);
}

function patchAction(path: string, payload?: AdminMutationPayload) {
  return adminApi.patch<AdminActionResponse>(path, payload);
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
  return useAdminPostAction("/api/v1/admin/impersonation/start", [["admin", "impersonation"]]);
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
