"use client";

import { createApiClient } from "@/lib/api";
import { useAppMutation, useAppQuery } from "@/lib/hooks/use-api";

export interface LocaleFileResponse {
  id: string;
  locale_code: string;
  version: number;
  translations: Record<string, unknown>;
  published_at: string | null;
  published_by: string | null;
  vendor_source_ref: string | null;
  created_at: string;
}

export type LocaleFileListItem = Omit<LocaleFileResponse, "translations">;

export interface LocaleFilePublishRequest {
  locale_code: string;
  translations: Record<string, unknown>;
  vendor_source_ref?: string | null;
}

const localesApi = createApiClient(process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000");

export const localesQueryKeys = {
  all: ["locales"] as const,
  file: (localeCode: string) => ["locales", localeCode] as const,
};

export function fetchAvailableLocales() {
  return localesApi.get<LocaleFileListItem[]>("/api/v1/locales", { skipAuth: true });
}

export function fetchLocaleFile(localeCode: string) {
  return localesApi.get<LocaleFileResponse>(`/api/v1/locales/${localeCode}`, {
    skipAuth: true,
  });
}

export function publishLocaleFile(payload: LocaleFilePublishRequest) {
  return localesApi.post<LocaleFileResponse>("/api/v1/admin/locales", payload);
}

export function useAvailableLocales() {
  return useAppQuery(localesQueryKeys.all, fetchAvailableLocales);
}

export function useLocaleFile(localeCode: string) {
  return useAppQuery(localesQueryKeys.file(localeCode), () => fetchLocaleFile(localeCode));
}

export function usePublishLocaleFile() {
  return useAppMutation(publishLocaleFile, {
    invalidateKeys: [localesQueryKeys.all],
  });
}

