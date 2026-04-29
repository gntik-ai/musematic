"use client";

import { create } from "zustand";
import { createJSONStorage, persist } from "zustand/middleware";

export interface ImpersonationSession {
  sessionId: string;
  impersonatingUsername: string;
  effectiveUsername: string;
  expiresAt: string;
}

interface AdminState {
  readOnlyMode: boolean;
  activeImpersonationSession: ImpersonationSession | null;
  twoPersonAuthNotificationsCount: number;
  firstInstallChecklistDismissed: boolean;
}

interface AdminActions {
  setReadOnlyMode: (readOnlyMode: boolean) => void;
  setActiveImpersonationSession: (session: ImpersonationSession | null) => void;
  incrementTwoPaNotifications: () => void;
  dismissChecklist: () => void;
}

const initialState: AdminState = {
  readOnlyMode: false,
  activeImpersonationSession: null,
  twoPersonAuthNotificationsCount: 0,
  firstInstallChecklistDismissed: false,
};

export const useAdminStore = create<AdminState & AdminActions>()(
  persist(
    (set) => ({
      ...initialState,
      setReadOnlyMode: (readOnlyMode) => set({ readOnlyMode }),
      setActiveImpersonationSession: (activeImpersonationSession) =>
        set({ activeImpersonationSession }),
      incrementTwoPaNotifications: () =>
        set((state) => ({
          twoPersonAuthNotificationsCount: state.twoPersonAuthNotificationsCount + 1,
        })),
      dismissChecklist: () => set({ firstInstallChecklistDismissed: true }),
    }),
    {
      name: "admin-workbench-storage",
      storage: createJSONStorage(() => localStorage),
      partialize: (state) => ({
        firstInstallChecklistDismissed: state.firstInstallChecklistDismissed,
      }),
    },
  ),
);
