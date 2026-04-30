"use client";

import { useInfiniteQuery, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  authorizeOAuthProvider,
  getAdminOAuthProviderHistory,
  getAdminOAuthProviderRateLimits,
  getAdminOAuthProviderStatus,
  linkOAuthProvider,
  listAdminOAuthProviders,
  listOAuthLinks,
  listOAuthProviders,
  putAdminOAuthProviderRateLimits,
  recoverWithOAuthProvider,
  reseedAdminOAuthProviderFromEnv,
  rotateAdminOAuthProviderSecret,
  testAdminOAuthProviderConnectivity,
  unlinkOAuthProvider,
  upsertAdminOAuthProvider,
} from "@/lib/api/auth";
import type {
  OAuthConfigReseedResponse,
  OAuthConnectivityTestResponse,
  OAuthAuthorizeResponse,
  OAuthHistoryListResponse,
  OAuthProviderAdminListResponse,
  OAuthProviderStatusResponse,
  OAuthProviderType,
  OAuthProviderUpsertRequest,
  OAuthRateLimitConfig,
} from "@/lib/types/oauth";

export const oauthQueryKeys = {
  adminProviders: () => ["oauth", "admin-providers"] as const,
  adminHistory: (providerType: OAuthProviderType) =>
    ["oauth", "admin-provider-history", providerType] as const,
  adminRateLimits: (providerType: OAuthProviderType) =>
    ["oauth", "admin-provider-rate-limits", providerType] as const,
  adminStatus: (providerType: OAuthProviderType) =>
    ["oauth", "admin-provider-status", providerType] as const,
  links: () => ["oauth", "links"] as const,
  publicProviders: () => ["oauth", "public-providers"] as const,
};

export function useOAuthProviders() {
  return useQuery({
    queryKey: oauthQueryKeys.publicProviders(),
    queryFn: listOAuthProviders,
    staleTime: 30_000,
  });
}

export function useOAuthLinks() {
  return useQuery({
    queryKey: oauthQueryKeys.links(),
    queryFn: listOAuthLinks,
  });
}

export function useAdminOAuthProviders() {
  return useQuery({
    queryKey: oauthQueryKeys.adminProviders(),
    queryFn: listAdminOAuthProviders,
  });
}

export function useAdminOAuthProviderStatus(providerType: OAuthProviderType) {
  return useQuery<OAuthProviderStatusResponse>({
    queryKey: oauthQueryKeys.adminStatus(providerType),
    queryFn: () => getAdminOAuthProviderStatus(providerType),
    staleTime: 60_000,
  });
}

export function useAdminOAuthProviderHistory(providerType: OAuthProviderType) {
  return useInfiniteQuery<OAuthHistoryListResponse>({
    queryKey: oauthQueryKeys.adminHistory(providerType),
    queryFn: ({ pageParam }) =>
      getAdminOAuthProviderHistory(
        providerType,
        typeof pageParam === "string" ? pageParam : null,
      ),
    getNextPageParam: (lastPage) => lastPage.next_cursor ?? undefined,
    initialPageParam: null,
  });
}

export function useAdminOAuthProviderRateLimits(providerType: OAuthProviderType) {
  return useQuery<OAuthRateLimitConfig>({
    queryKey: oauthQueryKeys.adminRateLimits(providerType),
    queryFn: () => getAdminOAuthProviderRateLimits(providerType),
  });
}

export function useOAuthAuthorizeMutation() {
  return useMutation<OAuthAuthorizeResponse, Error, OAuthProviderType>({
    mutationFn: authorizeOAuthProvider,
  });
}

export function useOAuthRecoveryMutation() {
  return useMutation<
    OAuthAuthorizeResponse,
    Error,
    { email: string; providerType: OAuthProviderType }
  >({
    mutationFn: ({ email, providerType }) =>
      recoverWithOAuthProvider(providerType, email),
  });
}

export function useOAuthLinkMutation() {
  return useMutation<OAuthAuthorizeResponse, Error, OAuthProviderType>({
    mutationFn: linkOAuthProvider,
  });
}

export function useOAuthUnlinkMutation() {
  const queryClient = useQueryClient();

  return useMutation<void, Error, OAuthProviderType>({
    mutationFn: unlinkOAuthProvider,
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: oauthQueryKeys.links() });
    },
  });
}

export function useAdminOAuthProviderMutation() {
  const queryClient = useQueryClient();

  return useMutation<
    OAuthProviderAdminListResponse["providers"][number],
    Error,
    { providerType: OAuthProviderType; payload: OAuthProviderUpsertRequest }
  >({
    mutationFn: ({ payload, providerType }) =>
      upsertAdminOAuthProvider(providerType, payload),
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: oauthQueryKeys.adminProviders() }),
        queryClient.invalidateQueries({ queryKey: oauthQueryKeys.publicProviders() }),
      ]);
    },
  });
}

export function useOAuthConnectivityMutation(providerType: OAuthProviderType) {
  return useMutation<OAuthConnectivityTestResponse, Error, void>({
    mutationFn: () => testAdminOAuthProviderConnectivity(providerType),
  });
}

export function useOAuthRotateSecretMutation(providerType: OAuthProviderType) {
  return useMutation<void, Error, string>({
    mutationFn: (newSecret) => rotateAdminOAuthProviderSecret(providerType, newSecret),
  });
}

export function useOAuthReseedMutation(providerType: OAuthProviderType) {
  const queryClient = useQueryClient();

  return useMutation<OAuthConfigReseedResponse, Error, boolean>({
    mutationFn: (forceUpdate) =>
      reseedAdminOAuthProviderFromEnv(providerType, forceUpdate),
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: oauthQueryKeys.adminProviders() }),
        queryClient.invalidateQueries({ queryKey: oauthQueryKeys.adminStatus(providerType) }),
        queryClient.invalidateQueries({ queryKey: oauthQueryKeys.adminHistory(providerType) }),
        queryClient.invalidateQueries({ queryKey: oauthQueryKeys.publicProviders() }),
      ]);
    },
  });
}

export function useOAuthRateLimitMutation(providerType: OAuthProviderType) {
  const queryClient = useQueryClient();

  return useMutation<OAuthRateLimitConfig, Error, OAuthRateLimitConfig>({
    mutationFn: (payload) => putAdminOAuthProviderRateLimits(providerType, payload),
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({
          queryKey: oauthQueryKeys.adminRateLimits(providerType),
        }),
        queryClient.invalidateQueries({ queryKey: oauthQueryKeys.adminHistory(providerType) }),
      ]);
    },
  });
}
