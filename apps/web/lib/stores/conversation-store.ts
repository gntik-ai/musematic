"use client";

import { create } from "zustand";
import type { ConversationBranch } from "@/types/conversations";

export interface BranchTab {
  id: string;
  name: string;
  interactionId: string | null;
}

export interface PendingOutboundMessage {
  id: string;
  content: string;
  conversationId: string;
  interactionId: string;
  isMidProcessInjection: boolean;
  retrying: boolean;
}

interface ConversationActions {
  setActiveBranch: (branchId: string | null) => void;
  setActiveInteraction: (interactionId: string | null) => void;
  setAgentProcessing: (processing: boolean, interactionId: string | null) => void;
  enableAutoScroll: () => void;
  pauseAutoScroll: () => void;
  incrementPending: () => void;
  clearPending: () => void;
  setGoalPanelOpen: (open: boolean) => void;
  setSelectedGoal: (goalId: string | null) => void;
  addBranchTab: (branch: ConversationBranch) => void;
  markInteractionUnread: (interactionId: string) => void;
  clearInteractionUnread: (interactionId: string) => void;
  markBranchUnread: (branchId: string) => void;
  clearBranchUnread: (branchId: string) => void;
  setRealtimeConnectionDegraded: (degraded: boolean) => void;
  queueOutboundMessage: (message: Omit<PendingOutboundMessage, "retrying">) => void;
  markOutboundMessageRetrying: (messageId: string, retrying: boolean) => void;
  removeOutboundMessage: (messageId: string) => void;
  hydrateFromConversation: (
    interactionId: string | null,
    branches: ConversationBranch[],
  ) => void;
  reset: () => void;
}

export interface ConversationStore {
  activeBranchId: string | null;
  activeInteractionId: string | null;
  branchTabs: BranchTab[];
  unreadInteractionIds: string[];
  unreadBranchIds: string[];
  isAgentProcessing: boolean;
  processingInteractionId: string | null;
  autoScrollEnabled: boolean;
  pendingMessageCount: number;
  goalPanelOpen: boolean;
  selectedGoalId: string | null;
  realtimeConnectionDegraded: boolean;
  pendingOutboundMessages: PendingOutboundMessage[];
}

const initialState: ConversationStore = {
  activeBranchId: null,
  activeInteractionId: null,
  branchTabs: [],
  unreadInteractionIds: [],
  unreadBranchIds: [],
  isAgentProcessing: false,
  processingInteractionId: null,
  autoScrollEnabled: true,
  pendingMessageCount: 0,
  goalPanelOpen: false,
  selectedGoalId: null,
  realtimeConnectionDegraded: false,
  pendingOutboundMessages: [],
};

export const useConversationStore = create<ConversationStore & ConversationActions>()(
  (set) => ({
    ...initialState,
    setActiveBranch: (activeBranchId) =>
      set((state) => ({
        activeBranchId,
        unreadBranchIds: activeBranchId
          ? state.unreadBranchIds.filter((id) => id !== activeBranchId)
          : state.unreadBranchIds,
      })),
    setActiveInteraction: (activeInteractionId) =>
      set((state) => ({
        activeInteractionId,
        unreadInteractionIds: activeInteractionId
          ? state.unreadInteractionIds.filter((id) => id !== activeInteractionId)
          : state.unreadInteractionIds,
      })),
    setAgentProcessing: (isAgentProcessing, processingInteractionId) =>
      set({ isAgentProcessing, processingInteractionId }),
    enableAutoScroll: () => set({ autoScrollEnabled: true }),
    pauseAutoScroll: () => set({ autoScrollEnabled: false }),
    incrementPending: () =>
      set((state) => ({ pendingMessageCount: state.pendingMessageCount + 1 })),
    clearPending: () => set({ pendingMessageCount: 0 }),
    setGoalPanelOpen: (goalPanelOpen) => set({ goalPanelOpen }),
    setSelectedGoal: (selectedGoalId) => set({ selectedGoalId }),
    addBranchTab: (branch) =>
      set((state) => {
        if (state.branchTabs.some((tab) => tab.id === branch.id)) {
          return state;
        }

        return {
          branchTabs: [
            ...state.branchTabs,
            { id: branch.id, name: branch.name, interactionId: null },
          ],
        };
      }),
    markInteractionUnread: (interactionId) =>
      set((state) => {
        if (
          state.activeInteractionId === interactionId &&
          state.activeBranchId === null
        ) {
          return state;
        }

        if (state.unreadInteractionIds.includes(interactionId)) {
          return state;
        }

        return {
          unreadInteractionIds: [...state.unreadInteractionIds, interactionId],
        };
      }),
    clearInteractionUnread: (interactionId) =>
      set((state) => ({
        unreadInteractionIds: state.unreadInteractionIds.filter(
          (id) => id !== interactionId,
        ),
      })),
    markBranchUnread: (branchId) =>
      set((state) => {
        if (state.activeBranchId === branchId || state.unreadBranchIds.includes(branchId)) {
          return state;
        }

        return {
          unreadBranchIds: [...state.unreadBranchIds, branchId],
        };
      }),
    clearBranchUnread: (branchId) =>
      set((state) => ({
        unreadBranchIds: state.unreadBranchIds.filter((id) => id !== branchId),
      })),
    setRealtimeConnectionDegraded: (realtimeConnectionDegraded) =>
      set({ realtimeConnectionDegraded }),
    queueOutboundMessage: (message) =>
      set((state) => {
        if (state.pendingOutboundMessages.some((item) => item.id === message.id)) {
          return state;
        }

        return {
          pendingOutboundMessages: [
            ...state.pendingOutboundMessages,
            { ...message, retrying: false },
          ],
        };
      }),
    markOutboundMessageRetrying: (messageId, retrying) =>
      set((state) => ({
        pendingOutboundMessages: state.pendingOutboundMessages.map((message) =>
          message.id === messageId ? { ...message, retrying } : message,
        ),
      })),
    removeOutboundMessage: (messageId) =>
      set((state) => ({
        pendingOutboundMessages: state.pendingOutboundMessages.filter(
          (message) => message.id !== messageId,
        ),
      })),
    hydrateFromConversation: (interactionId, branches) =>
      set({
        activeInteractionId: interactionId,
        branchTabs: branches.map((branch) => ({
          id: branch.id,
          name: branch.name,
          interactionId: null,
        })),
      }),
    reset: () => set({ ...initialState }),
  }),
);
