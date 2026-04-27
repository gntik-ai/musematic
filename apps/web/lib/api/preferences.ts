"use client";

import { createApiClient } from "@/lib/api";
import { useAppMutation, useAppQuery } from "@/lib/hooks/use-api";
import { queryClient } from "@/lib/query-client";

export type ThemePreference = "light" | "dark" | "system" | "high_contrast";
export type DataExportFormat = "json" | "csv" | "ndjson";

export interface UserPreferencesResponse {
  id: string | null;
  user_id: string;
  default_workspace_id: string | null;
  theme: ThemePreference;
  language: string;
  timezone: string;
  notification_preferences: Record<string, unknown>;
  data_export_format: DataExportFormat;
  is_persisted: boolean;
  created_at: string | null;
  updated_at: string | null;
}

export interface UserPreferencesUpdateRequest {
  theme?: ThemePreference;
  language?: string;
  timezone?: string;
  default_workspace_id?: string | null;
  notification_preferences?: Record<string, unknown>;
  data_export_format?: DataExportFormat;
}

const preferencesApi = createApiClient(process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000");

export const preferencesQueryKeys = {
  current: ["preferences", "current"] as const,
};

export function fetchUserPreferences() {
  return preferencesApi.get<UserPreferencesResponse>("/api/v1/me/preferences");
}

export function updateUserPreferences(payload: UserPreferencesUpdateRequest) {
  return preferencesApi.patch<UserPreferencesResponse>("/api/v1/me/preferences", payload);
}

export function useUserPreferences() {
  return useAppQuery(preferencesQueryKeys.current, fetchUserPreferences);
}

export function useUpdatePreferences() {
  return useAppMutation<
    UserPreferencesResponse,
    UserPreferencesUpdateRequest,
    { previous?: UserPreferencesResponse }
  >(updateUserPreferences, {
    onMutate: async (payload) => {
      await queryClient.cancelQueries({ queryKey: preferencesQueryKeys.current });
      const previous = queryClient.getQueryData<UserPreferencesResponse>(
        preferencesQueryKeys.current,
      );
      if (previous) {
        queryClient.setQueryData<UserPreferencesResponse>(preferencesQueryKeys.current, {
          ...previous,
          ...payload,
        });
        return { previous };
      }
      return {};
    },
    onError: (_error, _payload, context) => {
      if (context?.previous) {
        queryClient.setQueryData(preferencesQueryKeys.current, context.previous);
      }
    },
    invalidateKeys: [preferencesQueryKeys.current],
  });
}
