"use client";

import { useAppMutation, useAppQuery } from "@/lib/hooks/use-api";
import { queryClient } from "@/lib/query-client";
import {
  fetchUserSessions,
  meQueryKeys,
  revokeOtherSessions,
  revokeUserSession,
} from "@/lib/api/me";
import type { UserSessionListResponse } from "@/lib/schemas/me";

export function useUserSessions() {
  return useAppQuery(meQueryKeys.sessions, fetchUserSessions);
}

export function useRevokeSession() {
  return useAppMutation<void, string, { previous?: UserSessionListResponse }>(
    revokeUserSession,
    {
      onMutate: async (sessionId) => {
        await queryClient.cancelQueries({ queryKey: meQueryKeys.sessions });
        const previous = queryClient.getQueryData<UserSessionListResponse>(meQueryKeys.sessions);
        if (previous) {
          queryClient.setQueryData<UserSessionListResponse>(meQueryKeys.sessions, {
            items: previous.items.filter((item) => item.session_id !== sessionId),
          });
          return { previous };
        }
        return {};
      },
      onError: (_error, _sessionId, context) => {
        if (context?.previous) {
          queryClient.setQueryData(meQueryKeys.sessions, context.previous);
        }
      },
      invalidateKeys: [meQueryKeys.sessions],
    },
  );
}

export function useRevokeOtherSessions() {
  return useAppMutation(revokeOtherSessions, {
    onMutate: async () => {
      await queryClient.cancelQueries({ queryKey: meQueryKeys.sessions });
      const previous = queryClient.getQueryData<UserSessionListResponse>(meQueryKeys.sessions);
      if (previous) {
        queryClient.setQueryData<UserSessionListResponse>(meQueryKeys.sessions, {
          items: previous.items.filter((item) => item.is_current),
        });
        return { previous };
      }
      return {};
    },
    onError: (_error, _variables, context) => {
      if (context?.previous) {
        queryClient.setQueryData(meQueryKeys.sessions, context.previous);
      }
    },
    invalidateKeys: [meQueryKeys.sessions],
  });
}
