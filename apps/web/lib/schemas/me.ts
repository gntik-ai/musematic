"use client";

import { z } from "zod";

export const notificationChannelSchema = z.enum([
  "in_app",
  "email",
  "webhook",
  "slack",
  "teams",
  "sms",
]);

export const deliveryMethodSchema = notificationChannelSchema;
export const digestModeSchema = z.enum(["immediate", "hourly", "daily"]);
export const dsrRequestTypeSchema = z.enum([
  "access",
  "rectification",
  "erasure",
  "portability",
  "restriction",
  "objection",
]);
export const dsrStatusSchema = z.enum([
  "received",
  "scheduled_with_hold",
  "in_progress",
  "completed",
  "failed",
  "cancelled",
]);
export const consentTypeSchema = z.string().min(1);

export const userSessionDetailSchema = z.object({
  session_id: z.string().uuid(),
  device_info: z.string().nullable().optional(),
  ip_address: z.string().nullable().optional(),
  location: z.string().nullable().optional(),
  created_at: z.string().nullable().optional(),
  last_activity: z.string().nullable().optional(),
  is_current: z.boolean(),
});

export const userSessionListResponseSchema = z.object({
  items: z.array(userSessionDetailSchema),
});

export const revokeOtherSessionsResponseSchema = z.object({
  sessions_revoked: z.number().int().nonnegative(),
});

export const userServiceAccountSummarySchema = z.object({
  service_account_id: z.string().uuid(),
  name: z.string(),
  role: z.string(),
  status: z.string(),
  workspace_id: z.string().uuid().nullable().optional(),
  created_at: z.string(),
  last_used_at: z.string().nullable().optional(),
  api_key_prefix: z.string(),
});

export const userServiceAccountListResponseSchema = z.object({
  items: z.array(userServiceAccountSummarySchema),
  max_active: z.number().int().positive(),
});

export const userServiceAccountCreateRequestSchema = z.object({
  name: z.string().min(1).max(255),
  scopes: z.array(z.string().min(1)).default([]),
  expires_at: z.string().datetime().nullable().optional(),
  mfa_token: z.string().min(6).max(64).nullable().optional(),
});

export const userServiceAccountCreateResponseSchema = z.object({
  service_account_id: z.string().uuid(),
  name: z.string(),
  role: z.string(),
  api_key: z.string().min(1),
});

export const userConsentItemSchema = z.object({
  id: z.string().uuid(),
  consent_type: consentTypeSchema,
  granted: z.boolean(),
  granted_at: z.string(),
  revoked_at: z.string().nullable().optional(),
  workspace_id: z.string().uuid().nullable().optional(),
});

export const userConsentListResponseSchema = z.object({
  items: z.array(userConsentItemSchema),
});

export const userConsentRevokeRequestSchema = z.object({
  consent_type: consentTypeSchema,
});

export const userConsentHistoryResponseSchema = z.object({
  items: z.array(userConsentItemSchema),
});

export const userDsrSubmitRequestSchema = z.object({
  request_type: dsrRequestTypeSchema,
  legal_basis: z.string().max(256).nullable().optional(),
  hold_hours: z.number().int().min(0).max(72).default(0),
  confirm_text: z.string().max(32).nullable().optional(),
});

export const userDsrDetailResponseSchema = z.object({
  id: z.string().uuid(),
  subject_user_id: z.string().uuid(),
  request_type: dsrRequestTypeSchema,
  requested_by: z.string().uuid(),
  status: dsrStatusSchema.or(z.string()),
  legal_basis: z.string().nullable().optional(),
  scheduled_release_at: z.string().nullable().optional(),
  requested_at: z.string(),
  completed_at: z.string().nullable().optional(),
  completion_proof_hash: z.string().nullable().optional(),
  failure_reason: z.string().nullable().optional(),
  tombstone_id: z.string().uuid().nullable().optional(),
});

export const userDsrListResponseSchema = z.object({
  items: z.array(userDsrDetailResponseSchema),
  next_cursor: z.string().nullable().optional(),
});

export const userActivityItemSchema = z.object({
  id: z.string().uuid(),
  event_type: z.string().nullable().optional(),
  audit_event_source: z.string(),
  severity: z.string(),
  created_at: z.string(),
  canonical_payload: z.record(z.unknown()).nullable().optional(),
});

export const userActivityListResponseSchema = z.object({
  items: z.array(userActivityItemSchema),
  next_cursor: z.string().nullable().optional(),
});

export const quietHoursSchema = z.object({
  start_time: z.string(),
  end_time: z.string(),
  timezone: z.string(),
});

export const userNotificationPreferencesResponseSchema = z.object({
  state_transitions: z.array(z.string()),
  delivery_method: deliveryMethodSchema,
  webhook_url: z.string().nullable().optional(),
  per_channel_preferences: z.record(z.array(notificationChannelSchema)),
  digest_mode: z.record(digestModeSchema),
  quiet_hours: quietHoursSchema.nullable().optional(),
});

export const userNotificationPreferencesUpdateRequestSchema = z.object({
  state_transitions: z.array(z.string()).optional(),
  delivery_method: deliveryMethodSchema.optional(),
  webhook_url: z.string().nullable().optional(),
  per_channel_preferences: z.record(z.array(notificationChannelSchema)).optional(),
  digest_mode: z.record(digestModeSchema).optional(),
  quiet_hours: quietHoursSchema.nullable().optional(),
});

export const userNotificationTestResponseSchema = z.object({
  alert_id: z.string().uuid(),
  event_type: z.string(),
  delivery_method: deliveryMethodSchema,
  success: z.boolean(),
});

export const userAlertItemSchema = z.object({
  id: z.string().uuid(),
  alert_type: z.string(),
  title: z.string(),
  body: z.string().nullable().optional(),
  urgency: z.string(),
  read: z.boolean(),
  interaction_id: z.string().uuid().nullable().optional(),
  source_reference: z.record(z.unknown()).nullable().optional(),
  created_at: z.string(),
  updated_at: z.string().optional(),
});

export const userAlertListResponseSchema = z.object({
  items: z.array(userAlertItemSchema),
  next_cursor: z.string().nullable().optional(),
  total_unread: z.number().int().nonnegative(),
});

export const markAllReadResponseSchema = z.object({
  updated: z.number().int().nonnegative(),
  unread_count: z.number().int().nonnegative(),
});

export type NotificationChannel = z.infer<typeof notificationChannelSchema>;
export type DeliveryMethod = z.infer<typeof deliveryMethodSchema>;
export type DigestMode = z.infer<typeof digestModeSchema>;
export type UserSessionDetail = z.infer<typeof userSessionDetailSchema>;
export type UserSessionListResponse = z.infer<typeof userSessionListResponseSchema>;
export type RevokeOtherSessionsResponse = z.infer<typeof revokeOtherSessionsResponseSchema>;
export type UserServiceAccountSummary = z.infer<typeof userServiceAccountSummarySchema>;
export type UserServiceAccountListResponse = z.infer<typeof userServiceAccountListResponseSchema>;
export type UserServiceAccountCreateRequest = z.infer<
  typeof userServiceAccountCreateRequestSchema
>;
export type UserServiceAccountCreateResponse = z.infer<
  typeof userServiceAccountCreateResponseSchema
>;
export type UserConsentItem = z.infer<typeof userConsentItemSchema>;
export type UserConsentListResponse = z.infer<typeof userConsentListResponseSchema>;
export type UserConsentRevokeRequest = z.infer<typeof userConsentRevokeRequestSchema>;
export type UserConsentHistoryResponse = z.infer<typeof userConsentHistoryResponseSchema>;
export type UserDsrSubmitRequest = z.infer<typeof userDsrSubmitRequestSchema>;
export type UserDsrDetailResponse = z.infer<typeof userDsrDetailResponseSchema>;
export type UserDsrListResponse = z.infer<typeof userDsrListResponseSchema>;
export type UserActivityItem = z.infer<typeof userActivityItemSchema>;
export type UserActivityListResponse = z.infer<typeof userActivityListResponseSchema>;
export type QuietHours = z.infer<typeof quietHoursSchema>;
export type UserNotificationPreferencesResponse = z.infer<
  typeof userNotificationPreferencesResponseSchema
>;
export type UserNotificationPreferencesUpdateRequest = z.infer<
  typeof userNotificationPreferencesUpdateRequestSchema
>;
export type UserNotificationTestResponse = z.infer<typeof userNotificationTestResponseSchema>;
export type UserAlertItem = z.infer<typeof userAlertItemSchema>;
export type UserAlertListResponse = z.infer<typeof userAlertListResponseSchema>;
export type MarkAllReadResponse = z.infer<typeof markAllReadResponseSchema>;
