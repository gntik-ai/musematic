"use client";

import { useAppMutation } from "@/lib/hooks/use-api";
import {
  billingApi,
  type OverageAuthorizationState,
  workspaceBillingKeys,
} from "@/lib/hooks/use-workspace-billing";

interface AuthorizeOverageInput {
  workspaceId: string;
  max_overage_eur: string | null;
}

export function useAuthorizeOverage(workspaceId: string) {
  return useAppMutation<OverageAuthorizationState, AuthorizeOverageInput>(
    ({ workspaceId: id, max_overage_eur }) =>
      billingApi.post<OverageAuthorizationState>(
        `/api/v1/workspaces/${id}/billing/overage-authorization`,
        { max_overage_eur },
        { skipRetry: true },
      ),
    {
      invalidateKeys: [
        workspaceBillingKeys(workspaceId).summary,
        workspaceBillingKeys(workspaceId).overage,
      ],
    },
  );
}

export function useRevokeOverage(workspaceId: string) {
  return useAppMutation<void, string>(
    (id) =>
      billingApi.delete<void>(
        `/api/v1/workspaces/${id}/billing/overage-authorization`,
        { skipRetry: true },
      ),
    {
      invalidateKeys: [
        workspaceBillingKeys(workspaceId).summary,
        workspaceBillingKeys(workspaceId).overage,
      ],
    },
  );
}
