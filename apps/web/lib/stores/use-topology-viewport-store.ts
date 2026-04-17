"use client";

import { create } from "zustand";

export interface TopologyViewportState {
  viewport: { x: number; y: number; zoom: number } | null;
  selectedNodeId: string | null;
  expandedGroups: string[];
  setViewport: (viewport: { x: number; y: number; zoom: number }) => void;
  selectNode: (nodeId: string | null) => void;
  toggleGroup: (groupId: string) => void;
  reset: () => void;
}

const initialState = {
  viewport: null,
  selectedNodeId: null,
  expandedGroups: [],
};

export const useTopologyViewportStore = create<TopologyViewportState>()((set) => ({
  ...initialState,
  setViewport: (viewport) => set({ viewport }),
  selectNode: (selectedNodeId) => set({ selectedNodeId }),
  toggleGroup: (groupId) =>
    set((state) => ({
      expandedGroups: state.expandedGroups.includes(groupId)
        ? state.expandedGroups.filter((entry) => entry !== groupId)
        : [...state.expandedGroups, groupId],
    })),
  reset: () => set(initialState),
}));

