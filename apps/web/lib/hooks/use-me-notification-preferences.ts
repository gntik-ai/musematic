"use client";

import {
  fetchNotificationPreferences,
  meQueryKeys,
  sendTestNotification,
  updateNotificationPreferences,
} from "@/lib/api/me";
import { useAppMutation, useAppQuery } from "@/lib/hooks/use-api";

export function useNotificationPreferences() {
  return useAppQuery(meQueryKeys.notificationPreferences, fetchNotificationPreferences);
}

export function useUpdateNotificationPreferences() {
  return useAppMutation(updateNotificationPreferences, {
    invalidateKeys: [meQueryKeys.notificationPreferences],
  });
}

export function useTestNotification() {
  return useAppMutation(sendTestNotification);
}
