"use client";

import { markAllAlertsRead } from "@/lib/api/me";
import { useAppMutation } from "@/lib/hooks/use-api";

export function useMarkAllRead() {
  return useAppMutation(markAllAlertsRead, {
    invalidateKeys: [["me", "alerts"], ["alert-unread"]],
  });
}
