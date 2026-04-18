"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  authorizeOAuthProvider,
  linkOAuthProvider,
  listAdminOAuthProviders,
  listOAuthLinks,
  listOAuthProviders,
  unlinkOAuthProvider,
  upsertAdminOAuthProvider,
} from "@/lib/api/auth";
import type {
  OAuthAuthorizeResponse,
  OAuthProviderAdminListResponse,
  OAuthProviderType,
  OAuthProviderUpsertRequest,
} from "@/lib/types/oauth";

export const oauthQueryKeys = {
  adminProviders: () => ["oauth", "admin-providers"] as const,
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

export function useOAuthAuthorizeMutation() {
  return useMutation<OAuthAuthorizeResponse, Error, OAuthProviderType>({
    mutationFn: authorizeOAuthProvider,
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
