"use client";

import { previewContract } from "@/lib/api/creator-uis";
import { useAppMutation } from "@/lib/hooks/use-api";

export function useContractPreview(contractId?: string | null) {
  return useAppMutation(
    async (payload: {
      sampleInput: Record<string, unknown>;
      useMock?: boolean;
      costAcknowledged?: boolean;
    }) => {
      if (!contractId) {
        throw new Error("contractId is required");
      }
      return previewContract(
        contractId,
        payload.sampleInput,
        payload.useMock ?? true,
        payload.costAcknowledged ?? false,
      );
    },
  );
}

