"use client";

import { create } from "zustand";
import { persist, createJSONStorage } from "zustand/middleware";
import type { AuthSession, AuthState, TokenPair, UserProfile } from "@/types/auth";

interface AuthActions {
  setTokens: (tokens: TokenPair) => void;
  setUser: (user: UserProfile) => void;
  setAuth: (session: AuthSession) => void;
  clearAuth: () => void;
  setLoading: (loading: boolean) => void;
  setHasHydrated: (hasHydrated: boolean) => void;
}

interface AuthHydrationState {
  hasHydrated: boolean;
}

export type AuthStore = AuthState & AuthHydrationState & AuthActions;

const initialState: AuthState = {
  user: null,
  accessToken: null,
  refreshToken: null,
  isAuthenticated: false,
  isLoading: false,
};

export function mergePersistedAuthState(
  persistedState: unknown,
  currentState: AuthStore,
): AuthStore {
  const hydratedState = {
    ...currentState,
    ...(persistedState as Partial<AuthState> | undefined),
  };

  return {
    ...hydratedState,
    hasHydrated: true,
    isAuthenticated: Boolean(
      hydratedState.refreshToken ?? hydratedState.accessToken ?? hydratedState.user,
    ),
  };
}

export const useAuthStore = create<AuthStore>()(
  persist(
    (set) => ({
      ...initialState,
      hasHydrated: false,
      setTokens: (tokens) =>
        set((state) => ({
          ...state,
          accessToken: tokens.accessToken,
          refreshToken: tokens.refreshToken,
          isAuthenticated: state.user !== null || tokens.accessToken.length > 0,
        })),
      setUser: (user) =>
        set((state) => ({
          ...state,
          user,
          isAuthenticated: true,
        })),
      setAuth: ({ user, accessToken, refreshToken }) =>
        set((state) => ({
          ...state,
          user,
          accessToken,
          refreshToken,
          isAuthenticated: true,
        })),
      clearAuth: () => set({ ...initialState, hasHydrated: true }),
      setLoading: (loading) => set({ isLoading: loading }),
      setHasHydrated: (hasHydrated) => set({ hasHydrated }),
    }),
    {
      name: "auth-storage",
      storage: createJSONStorage(() => localStorage),
      partialize: (state) => ({
        refreshToken: state.refreshToken,
        user: state.user,
      }),
      merge: mergePersistedAuthState,
      onRehydrateStorage: () => (state) => {
        state?.setHasHydrated(true);
      },
    },
  ),
);
