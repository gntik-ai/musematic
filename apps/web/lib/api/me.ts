"use client";

import { createApiClient } from "@/lib/api";
import {
  markAllReadResponseSchema,
  revokeOtherSessionsResponseSchema,
  userActivityListResponseSchema,
  userAlertListResponseSchema,
  userConsentHistoryResponseSchema,
  userConsentListResponseSchema,
  userDsrDetailResponseSchema,
  userDsrListResponseSchema,
  userNotificationPreferencesResponseSchema,
  userNotificationPreferencesUpdateRequestSchema,
  userNotificationTestResponseSchema,
  userServiceAccountCreateRequestSchema,
  userServiceAccountCreateResponseSchema,
  userServiceAccountListResponseSchema,
  userSessionListResponseSchema,
  type MarkAllReadResponse,
  type RevokeOtherSessionsResponse,
  type UserActivityListResponse,
  type UserAlertListResponse,
  type UserConsentHistoryResponse,
  type UserConsentListResponse,
  type UserConsentRevokeRequest,
  type UserDsrDetailResponse,
  type UserDsrListResponse,
  type UserDsrSubmitRequest,
  type UserNotificationPreferencesResponse,
  type UserNotificationPreferencesUpdateRequest,
  type UserNotificationTestResponse,
  type UserServiceAccountCreateRequest,
  type UserServiceAccountCreateResponse,
  type UserServiceAccountListResponse,
  type UserSessionListResponse,
} from "@/lib/schemas/me";
import type { ZodType } from "zod";

const api = createApiClient(process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000");

function buildQuery(params: Record<string, string | number | boolean | null | undefined>): string {
  const query = new URLSearchParams();
  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== "") {
      query.set(key, String(value));
    }
  });
  const serialized = query.toString();
  return serialized ? `?${serialized}` : "";
}

async function parseWith<T>(schema: ZodType<T>, promise: Promise<unknown>): Promise<T> {
  return schema.parse(await promise);
}

export const meQueryKeys = {
  sessions: ["me", "sessions"] as const,
  serviceAccounts: ["me", "service-accounts"] as const,
  consents: ["me", "consent"] as const,
  consentHistory: ["me", "consent", "history"] as const,
  dsrs: (cursor?: string | null) => ["me", "dsr", cursor ?? null] as const,
  dsr: (id: string | null) => ["me", "dsr", id] as const,
  activity: (filters?: UserActivityFilters) => ["me", "activity", filters ?? {}] as const,
  notificationPreferences: ["me", "notification-preferences"] as const,
  alerts: (filters?: UserAlertFilters) => ["me", "alerts", filters ?? {}] as const,
};

export interface UserActivityFilters {
  start_ts?: string | null;
  end_ts?: string | null;
  event_type?: string | null;
  limit?: number;
}

export interface UserAlertFilters {
  read?: "all" | "read" | "unread";
  limit?: number;
  cursor?: string | null;
}

export function fetchUserSessions(): Promise<UserSessionListResponse> {
  return parseWith(userSessionListResponseSchema, api.get("/api/v1/me/sessions"));
}

export function revokeUserSession(sessionId: string): Promise<void> {
  return api.delete<void>(`/api/v1/me/sessions/${sessionId}`);
}

export function revokeOtherSessions(): Promise<RevokeOtherSessionsResponse> {
  return parseWith(
    revokeOtherSessionsResponseSchema,
    api.post("/api/v1/me/sessions/revoke-others"),
  );
}

export function fetchUserServiceAccounts(): Promise<UserServiceAccountListResponse> {
  return parseWith(
    userServiceAccountListResponseSchema,
    api.get("/api/v1/me/service-accounts"),
  );
}

export function createUserServiceAccount(
  payload: UserServiceAccountCreateRequest,
): Promise<UserServiceAccountCreateResponse> {
  return parseWith(
    userServiceAccountCreateResponseSchema,
    api.post("/api/v1/me/service-accounts", userServiceAccountCreateRequestSchema.parse(payload)),
  );
}

export function revokeUserServiceAccount(serviceAccountId: string): Promise<void> {
  return api.delete<void>(`/api/v1/me/service-accounts/${serviceAccountId}`);
}

export function fetchUserConsents(): Promise<UserConsentListResponse> {
  return parseWith(userConsentListResponseSchema, api.get("/api/v1/me/consent"));
}

export function revokeUserConsent(payload: UserConsentRevokeRequest) {
  return api.post("/api/v1/me/consent/revoke", payload);
}

export function fetchUserConsentHistory(): Promise<UserConsentHistoryResponse> {
  return parseWith(userConsentHistoryResponseSchema, api.get("/api/v1/me/consent/history"));
}

export function submitUserDsr(payload: UserDsrSubmitRequest): Promise<UserDsrDetailResponse> {
  return parseWith(userDsrDetailResponseSchema, api.post("/api/v1/me/dsr", payload));
}

export function fetchUserDsrs(
  params: { limit?: number; cursor?: string | null } = {},
): Promise<UserDsrListResponse> {
  return parseWith(
    userDsrListResponseSchema,
    api.get(`/api/v1/me/dsr${buildQuery({ limit: params.limit ?? 20, cursor: params.cursor })}`),
  );
}

export function fetchUserDsr(id: string): Promise<UserDsrDetailResponse> {
  return parseWith(userDsrDetailResponseSchema, api.get(`/api/v1/me/dsr/${id}`));
}

export function fetchUserActivity(
  filters: UserActivityFilters = {},
  cursor?: string | null,
): Promise<UserActivityListResponse> {
  return parseWith(
    userActivityListResponseSchema,
    api.get(
      `/api/v1/me/activity${buildQuery({
        ...filters,
        cursor,
        limit: filters.limit ?? 20,
      })}`,
    ),
  );
}

export function fetchNotificationPreferences(): Promise<UserNotificationPreferencesResponse> {
  return parseWith(
    userNotificationPreferencesResponseSchema,
    api.get("/api/v1/me/notification-preferences"),
  );
}

export function updateNotificationPreferences(
  payload: UserNotificationPreferencesUpdateRequest,
): Promise<UserNotificationPreferencesResponse> {
  return parseWith(
    userNotificationPreferencesResponseSchema,
    api.put(
      "/api/v1/me/notification-preferences",
      userNotificationPreferencesUpdateRequestSchema.parse(payload),
    ),
  );
}

export function sendTestNotification(eventType: string): Promise<UserNotificationTestResponse> {
  return parseWith(
    userNotificationTestResponseSchema,
    api.post(`/api/v1/me/notification-preferences/test/${encodeURIComponent(eventType)}`),
  );
}

export function fetchUserAlerts(filters: UserAlertFilters = {}): Promise<UserAlertListResponse> {
  return parseWith(
    userAlertListResponseSchema,
    api.get(
      `/api/v1/me/alerts${buildQuery({
        read: filters.read ?? "all",
        limit: filters.limit ?? 20,
        cursor: filters.cursor,
      })}`,
    ),
  );
}

export function markAllAlertsRead(): Promise<MarkAllReadResponse> {
  return parseWith(markAllReadResponseSchema, api.post("/api/v1/me/alerts/mark-all-read"));
}
