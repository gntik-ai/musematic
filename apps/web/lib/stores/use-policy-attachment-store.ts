"use client";

import { create } from "zustand";

interface PolicyAttachmentStore {
  isDragging: boolean;
  draggedPolicyId: string | null;
  draggedPolicyName: string | null;
  dropError: string | null;
  startDrag: (policyId: string, policyName: string) => void;
  endDrag: () => void;
  setDropError: (error: string) => void;
  clearDropError: () => void;
}

const initialState = {
  isDragging: false,
  draggedPolicyId: null,
  draggedPolicyName: null,
  dropError: null,
} satisfies Pick<
  PolicyAttachmentStore,
  "isDragging" | "draggedPolicyId" | "draggedPolicyName" | "dropError"
>;

export const usePolicyAttachmentStore = create<PolicyAttachmentStore>()((set) => ({
  ...initialState,
  startDrag: (policyId, policyName) =>
    set({
      isDragging: true,
      draggedPolicyId: policyId,
      draggedPolicyName: policyName,
      dropError: null,
    }),
  endDrag: () => set({ ...initialState }),
  setDropError: (error) => set({ dropError: error }),
  clearDropError: () => set({ dropError: null }),
}));
