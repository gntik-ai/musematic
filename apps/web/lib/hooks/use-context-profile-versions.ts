"use client";

import {
  fetchProfileVersionDiff,
  fetchProfileVersions,
  rollbackProfileVersion,
} from "@/lib/api/creator-uis";
import { useAppMutation, useAppQuery } from "@/lib/hooks/use-api";

export function useContextProfileVersions(
  workspaceId?: string | null,
  profileId?: string | null,
) {
  return useAppQuery(
    ["context-profile-versions", workspaceId ?? "none", profileId ?? "none"],
    () => fetchProfileVersions(workspaceId ?? "", profileId ?? ""),
    { enabled: Boolean(workspaceId && profileId) },
  );
}

export function useContextProfileVersionDiff(
  workspaceId: string | null | undefined,
  profileId: string | null | undefined,
  baseVersion: number | null,
  compareVersion: number | null,
) {
  return useAppQuery(
    [
      "context-profile-version-diff",
      workspaceId ?? "none",
      profileId ?? "none",
      baseVersion ?? "none",
      compareVersion ?? "none",
    ],
    () =>
      fetchProfileVersionDiff(
        workspaceId ?? "",
        profileId ?? "",
        baseVersion ?? 1,
        compareVersion ?? 1,
      ),
    { enabled: Boolean(workspaceId && profileId && baseVersion && compareVersion) },
  );
}

export function useRollbackProfileVersion(
  workspaceId?: string | null,
  profileId?: string | null,
) {
  return useAppMutation(
    async (version: number) => {
      if (!workspaceId || !profileId) {
        throw new Error("workspaceId and profileId are required");
      }
      return rollbackProfileVersion(workspaceId, profileId, version);
    },
    {
      invalidateKeys: [["context-profile-versions", workspaceId ?? "none", profileId ?? "none"]],
    },
  );
}

