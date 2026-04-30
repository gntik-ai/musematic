"use client";

import {
  createUserServiceAccount,
  fetchUserServiceAccounts,
  meQueryKeys,
  revokeUserServiceAccount,
} from "@/lib/api/me";
import { useAppMutation, useAppQuery } from "@/lib/hooks/use-api";
import type { UserServiceAccountCreateRequest } from "@/lib/schemas/me";

export function useUserApiKeys() {
  return useAppQuery(meQueryKeys.serviceAccounts, fetchUserServiceAccounts);
}

export function useCreateApiKey() {
  return useAppMutation(createUserServiceAccount, {
    invalidateKeys: [meQueryKeys.serviceAccounts],
  });
}

export function useCreateApiKeyWithMfaToken() {
  const mutation = useCreateApiKey();
  return (payload: UserServiceAccountCreateRequest, mfaToken: string) =>
    mutation.mutate({ ...payload, mfa_token: mfaToken });
}

export function useRevokeApiKey() {
  return useAppMutation<void, string>(revokeUserServiceAccount, {
    invalidateKeys: [meQueryKeys.serviceAccounts],
  });
}
