"use client";

import {
  fetchUserConsentHistory,
  fetchUserConsents,
  meQueryKeys,
  revokeUserConsent,
} from "@/lib/api/me";
import { useAppMutation, useAppQuery } from "@/lib/hooks/use-api";

export function useUserConsents() {
  return useAppQuery(meQueryKeys.consents, fetchUserConsents);
}

export function useRevokeConsent() {
  return useAppMutation(revokeUserConsent, {
    invalidateKeys: [meQueryKeys.consents, meQueryKeys.consentHistory],
  });
}

export function useConsentHistory() {
  return useAppQuery(meQueryKeys.consentHistory, fetchUserConsentHistory);
}
