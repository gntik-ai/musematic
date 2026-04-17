"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { ApiError } from "@/types/api";
import { certificationQueryKeys, trustWorkbenchApi } from "@/lib/hooks/use-certifications";
import { useAuthStore } from "@/store/auth-store";
import type { CertificationDetail, EvidenceItem } from "@/lib/types/trust-workbench";

interface EvidenceRefInput {
  certificationId: string;
  reviewerId?: string | null;
  notes: string;
  storageRef?: string | null;
}

type ApproveCertificationInput = EvidenceRefInput;

interface RevokeCertificationInput {
  certificationId: string;
  notes: string;
}

type MutationConflictError = Error & { conflictError?: boolean };

function withConflictMetadata(error: unknown): never {
  if (error instanceof ApiError && error.status === 409) {
    const conflict = new Error(error.message) as MutationConflictError;
    conflict.conflictError = true;
    throw conflict;
  }

  throw error;
}

function buildStorageRef(
  files: File[] | undefined,
  explicitStorageRef?: string | null,
): string | null {
  if (explicitStorageRef) {
    return explicitStorageRef;
  }
  if (!files || files.length === 0) {
    return null;
  }

  return `review-upload:${files
    .map((file) => `${file.name}:${file.size}`)
    .join(",")}`;
}

export function useAddEvidenceRef(certificationId?: string) {
  const reviewerId = useAuthStore((state) => state.user?.id ?? null);
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (variables: EvidenceRefInput) => {
      try {
        const resolvedCertificationId =
          certificationId ?? variables.certificationId;

        return await trustWorkbenchApi.post<EvidenceItem>(
          `/api/v1/trust/certifications/${encodeURIComponent(resolvedCertificationId)}/evidence`,
          {
            evidenceType: "manual_review",
            sourceRefType: "reviewer_decision",
            sourceRefId: variables.reviewerId ?? reviewerId ?? "unknown-reviewer",
            summary: variables.notes,
            storageRef: variables.storageRef ?? null,
          },
        );
      } catch (error) {
        withConflictMetadata(error);
      }
    },
    onSuccess: async (_, variables) => {
      await queryClient.invalidateQueries({
        queryKey: certificationQueryKeys.detail(
          certificationId ?? variables.certificationId,
        ),
      });
    },
  });
}

export function useApproveCertification() {
  const reviewerId = useAuthStore((state) => state.user?.id ?? null);
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (
      variables: ApproveCertificationInput & { files?: File[] },
    ) => {
      try {
        const detail = await trustWorkbenchApi.post<CertificationDetail>(
          `/api/v1/trust/certifications/${encodeURIComponent(variables.certificationId)}/activate`,
        );

        try {
          await trustWorkbenchApi.post<EvidenceItem>(
            `/api/v1/trust/certifications/${encodeURIComponent(variables.certificationId)}/evidence`,
            {
              evidenceType: "manual_review",
              sourceRefType: "reviewer_decision",
              sourceRefId: variables.reviewerId ?? reviewerId ?? "unknown-reviewer",
              summary: variables.notes,
              storageRef: buildStorageRef(variables.files, variables.storageRef),
            },
          );
        } catch (evidenceError) {
          console.error("Unable to persist manual review evidence", evidenceError);
        }

        return detail;
      } catch (error) {
        withConflictMetadata(error);
      }
    },
    onSettled: async (_, __, variables) => {
      await Promise.all([
        queryClient.invalidateQueries({
          queryKey: certificationQueryKeys.detail(variables.certificationId),
        }),
        queryClient.invalidateQueries({
          queryKey: certificationQueryKeys.root,
        }),
      ]);
    },
  });
}

export function useRevokeCertification() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (variables: RevokeCertificationInput) => {
      try {
        return await trustWorkbenchApi.post<CertificationDetail>(
          `/api/v1/trust/certifications/${encodeURIComponent(variables.certificationId)}/revoke`,
          { reason: variables.notes },
        );
      } catch (error) {
        withConflictMetadata(error);
      }
    },
    onSettled: async (_, __, variables) => {
      await Promise.all([
        queryClient.invalidateQueries({
          queryKey: certificationQueryKeys.detail(variables.certificationId),
        }),
        queryClient.invalidateQueries({
          queryKey: certificationQueryKeys.root,
        }),
      ]);
    },
  });
}
