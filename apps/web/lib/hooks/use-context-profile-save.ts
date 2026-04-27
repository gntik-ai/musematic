"use client";

import {
  createContextProfile,
  type ContextProfilePayload,
  updateContextProfile,
} from "@/lib/api/creator-uis";
import { useAppMutation } from "@/lib/hooks/use-api";

export function useContextProfileSave(workspaceId?: string | null, profileId?: string | null) {
  return useAppMutation(async (payload: ContextProfilePayload) => {
    if (!workspaceId) {
      throw new Error("workspaceId is required");
    }

    if (profileId) {
      return updateContextProfile(workspaceId, profileId, payload);
    }

    return createContextProfile(workspaceId, payload);
  });
}
