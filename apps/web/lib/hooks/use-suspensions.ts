"use client";

/**
 * UPD-050 — TanStack Query hooks for the platform-staff suspension
 * queue (US4).
 *
 * Endpoints under `/api/v1/admin/security/suspensions/*` per
 * `specs/100-abuse-prevention/contracts/admin-security-rest.md`.
 */

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { createApiClient } from "@/lib/api";
import { useAppQuery } from "@/lib/hooks/use-api";
import type {
  SuspensionCreateRequest,
  SuspensionDetailView,
  SuspensionLiftRequest,
  SuspensionView,
} from "@/lib/security/types";

const adminApi = createApiClient(
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000",
);

export const suspensionKeys = {
  list: (status?: string) => ["admin", "security", "suspensions", status ?? "active"] as const,
  detail: (id: string) => ["admin", "security", "suspensions", "detail", id] as const,
};

interface SuspensionListResponse {
  items: SuspensionView[];
}

export function useSuspensions(status: "active" | "lifted" | "all" = "active") {
  return useAppQuery<SuspensionListResponse>(
    suspensionKeys.list(status),
    () =>
      adminApi.get<SuspensionListResponse>(
        `/api/v1/admin/security/suspensions?status=${status}&limit=50`,
      ),
  );
}

export function useSuspensionDetail(id: string) {
  return useAppQuery<SuspensionDetailView>(
    suspensionKeys.detail(id),
    () =>
      adminApi.get<SuspensionDetailView>(
        `/api/v1/admin/security/suspensions/${id}`,
      ),
  );
}

function invalidateSuspensions(client: ReturnType<typeof useQueryClient>) {
  client.invalidateQueries({
    queryKey: ["admin", "security", "suspensions"],
  });
}

export function useLiftSuspension() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: async (input: { id: string; body: SuspensionLiftRequest }) =>
      adminApi.post(
        `/api/v1/admin/security/suspensions/${input.id}/lift`,
        input.body,
      ),
    onSuccess: () => invalidateSuspensions(client),
  });
}

export function useCreateSuspension() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: async (body: SuspensionCreateRequest) =>
      adminApi.post(`/api/v1/admin/security/suspensions`, body),
    onSuccess: () => invalidateSuspensions(client),
  });
}
