"use client";

import { previewContextProfile } from "@/lib/api/creator-uis";
import { useAppMutation } from "@/lib/hooks/use-api";

export function useContextProfilePreview(workspaceId?: string | null, profileId?: string | null) {
  return useAppMutation(async (queryText: string) => {
    if (!workspaceId || !profileId) {
      throw new Error("workspaceId and profileId are required");
    }
    return previewContextProfile(workspaceId, profileId, queryText);
  });
}

