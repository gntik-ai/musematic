"use client";

import { create } from "zustand";
import { persist, createJSONStorage } from "zustand/middleware";
import { queryClient } from "@/lib/query-client";
import type { Workspace, WorkspaceState } from "@/types/workspace";

interface WorkspaceActions {
  setCurrentWorkspace: (workspace: Workspace) => void;
  setWorkspaceList: (list: Workspace[]) => void;
  setSidebarCollapsed: (collapsed: boolean) => void;
  setLoading: (loading: boolean) => void;
}

export type WorkspaceStore = WorkspaceState & WorkspaceActions;

const initialState: WorkspaceState = {
  currentWorkspace: null,
  workspaceList: [],
  sidebarCollapsed: false,
  isLoading: false,
};

export const useWorkspaceStore = create<WorkspaceStore>()(
  persist(
    (set) => ({
      ...initialState,
      setCurrentWorkspace: (workspace) => {
        set({ currentWorkspace: workspace });
        void queryClient.invalidateQueries();
      },
      setWorkspaceList: (workspaceList) => set({ workspaceList }),
      setSidebarCollapsed: (sidebarCollapsed) => set({ sidebarCollapsed }),
      setLoading: (isLoading) => set({ isLoading }),
    }),
    {
      name: "workspace-storage",
      storage: createJSONStorage(() => localStorage),
      partialize: (state) => ({
        currentWorkspace: state.currentWorkspace,
        sidebarCollapsed: state.sidebarCollapsed,
      }),
    },
  ),
);
