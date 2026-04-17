"use client";

import { useEffect, useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { createApiClient } from "@/lib/api";
import { useAuthStore } from "@/store/auth-store";
import { useWorkspaceStore } from "@/store/workspace-store";
import type { PaginatedResponse } from "@/types/api";
import type { Workspace } from "@/types/workspace";

const workspaceApi = createApiClient(
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000",
);

type WorkspaceCollection = PaginatedResponse<Workspace> | { items: Workspace[] };
const EMPTY_WORKSPACES: Workspace[] = [];

function normalizeWorkspaces(payload: WorkspaceCollection): Workspace[] {
  return payload.items;
}

export interface UseWorkspacesOptions {
  enabled?: boolean;
}

export function useWorkspaces(options: UseWorkspacesOptions = {}) {
  const userWorkspaceId = useAuthStore((state) => state.user?.workspaceId ?? null);
  const currentWorkspace = useWorkspaceStore((state) => state.currentWorkspace);
  const setCurrentWorkspace = useWorkspaceStore((state) => state.setCurrentWorkspace);
  const setWorkspaceList = useWorkspaceStore((state) => state.setWorkspaceList);
  const enabled = options.enabled ?? true;

  const query = useQuery({
    queryKey: ["workspaces"],
    queryFn: () => workspaceApi.get<WorkspaceCollection>("/api/v1/workspaces"),
    staleTime: 60_000,
    enabled,
  });

  const workspaces = useMemo(
    () => (query.data ? normalizeWorkspaces(query.data) : EMPTY_WORKSPACES),
    [query.data],
  );

  useEffect(() => {
    if (!enabled || workspaces.length === 0) {
      return;
    }

    setWorkspaceList(workspaces);

    if (currentWorkspace) {
      return;
    }

    const preferredWorkspace =
      workspaces.find((workspace) => workspace.id === userWorkspaceId) ??
      workspaces[0];

    if (preferredWorkspace) {
      setCurrentWorkspace(preferredWorkspace);
    }
  }, [
    currentWorkspace,
    setCurrentWorkspace,
    setWorkspaceList,
    userWorkspaceId,
    workspaces,
  ]);

  return {
    ...query,
    enabled,
    workspaces,
  };
}
