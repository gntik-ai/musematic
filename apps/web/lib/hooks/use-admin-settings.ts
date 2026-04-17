"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { createApiClient } from "@/lib/api";
import type {
  AdminUserRow,
  AdminUsersParams,
  AdminUsersResponse,
  ConnectorTypeGlobalConfig,
  DefaultQuotas,
  EmailDeliveryConfig,
  SecurityPolicySettings,
  SignupPolicySettings,
  TestEmailResult,
  UserAction,
  WorkspaceQuotaOverride,
  WorkspaceSearchResponse,
} from "@/lib/types/admin";

const adminApi = createApiClient(
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000",
);

export const adminQueryKeys = {
  users: (params: AdminUsersParams) => ["admin", "users", params] as const,
  signupPolicy: () => ["admin", "settings", "signup"] as const,
  defaultQuotas: () => ["admin", "settings", "quotas"] as const,
  workspaceQuota: (workspaceId: string) =>
    ["admin", "settings", "quotas", workspaceId] as const,
  workspaces: (search: string) => ["admin", "workspaces", search] as const,
  connectorTypes: () => ["admin", "settings", "connectors"] as const,
  emailConfig: () => ["admin", "settings", "email"] as const,
  securityPolicy: () => ["admin", "settings", "security"] as const,
};

interface VersionedMutationPayload<TBody> {
  body: TBody;
  _version: string;
}

function buildQueryString(
  params: Record<string, string | number | undefined | null>,
): string {
  const searchParams = new URLSearchParams();

  for (const [key, value] of Object.entries(params)) {
    if (value === undefined || value === null || value === "") {
      continue;
    }
    searchParams.set(key, String(value));
  }

  const query = searchParams.toString();
  return query ? `?${query}` : "";
}

function getUserActionsForStatus(status: AdminUserRow["status"]): UserAction[] {
  switch (status) {
    case "pending_approval":
      return ["approve", "reject"];
    case "active":
      return ["suspend"];
    case "suspended":
      return ["reactivate"];
    default:
      return [];
  }
}

function getNextStatus(action: UserAction): AdminUserRow["status"] {
  switch (action) {
    case "approve":
    case "reactivate":
      return "active";
    case "reject":
      return "blocked";
    case "suspend":
      return "suspended";
  }
}

function updateUsersResponse(
  response: AdminUsersResponse | undefined,
  userId: string,
  action: UserAction,
): AdminUsersResponse | undefined {
  if (!response) {
    return response;
  }

  return {
    ...response,
    items: response.items.map((user) => {
      if (user.id !== userId) {
        return user;
      }

      const status = getNextStatus(action);
      return {
        ...user,
        status,
        available_actions: getUserActionsForStatus(status),
      };
    }),
  };
}

async function patchWithVersion<TResponse, TBody>(
  path: string,
  payload: VersionedMutationPayload<TBody>,
): Promise<TResponse> {
  return adminApi.patch<TResponse>(path, payload.body, {
    headers: {
      "If-Unmodified-Since": payload._version,
    },
  });
}

export function useAdminUsers(params: AdminUsersParams) {
  return useQuery({
    queryKey: adminQueryKeys.users(params),
    queryFn: () =>
      adminApi.get<AdminUsersResponse>(
        `/api/v1/admin/users${buildQueryString({
          search: params.search,
          status: params.status === "all" ? undefined : params.status,
          page: params.page ?? 1,
          page_size: params.page_size ?? 20,
          sort: params.sort,
        })}`,
      ),
    staleTime: 30_000,
  });
}

export function useUserActionMutation(userId: string) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (action: UserAction) =>
      adminApi.post<void>(`/api/v1/admin/users/${userId}/${action}`),
    onMutate: async (action) => {
      await queryClient.cancelQueries({ queryKey: ["admin", "users"] });

      const previousEntries = queryClient.getQueriesData<AdminUsersResponse>({
        queryKey: ["admin", "users"],
      });

      for (const [queryKey, response] of previousEntries) {
        queryClient.setQueryData<AdminUsersResponse>(
          queryKey,
          updateUsersResponse(response, userId, action),
        );
      }

      return { previousEntries };
    },
    onError: (_error, _action, context) => {
      for (const [queryKey, response] of context?.previousEntries ?? []) {
        queryClient.setQueryData(queryKey, response);
      }
    },
    onSettled: async () => {
      await queryClient.invalidateQueries({ queryKey: ["admin", "users"] });
    },
  });
}

export function useSignupPolicy() {
  return useQuery({
    queryKey: adminQueryKeys.signupPolicy(),
    queryFn: () =>
      adminApi.get<SignupPolicySettings>("/api/v1/admin/settings/signup"),
  });
}

export function useSignupPolicyMutation() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (payload: VersionedMutationPayload<Omit<SignupPolicySettings, "updated_at">>) =>
      patchWithVersion<SignupPolicySettings, Omit<SignupPolicySettings, "updated_at">>(
        "/api/v1/admin/settings/signup",
        payload,
      ),
    onSuccess: async () => {
      await queryClient.invalidateQueries({
        queryKey: adminQueryKeys.signupPolicy(),
      });
    },
  });
}

export function useDefaultQuotas() {
  return useQuery({
    queryKey: adminQueryKeys.defaultQuotas(),
    queryFn: () =>
      adminApi.get<DefaultQuotas>("/api/v1/admin/settings/quotas"),
  });
}

export function useDefaultQuotasMutation() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (payload: VersionedMutationPayload<Omit<DefaultQuotas, "updated_at">>) =>
      patchWithVersion<DefaultQuotas, Omit<DefaultQuotas, "updated_at">>(
        "/api/v1/admin/settings/quotas",
        payload,
      ),
    onSuccess: async () => {
      await queryClient.invalidateQueries({
        queryKey: adminQueryKeys.defaultQuotas(),
      });
    },
  });
}

export function useAdminWorkspaces(search: string) {
  return useQuery({
    queryKey: adminQueryKeys.workspaces(search),
    queryFn: () =>
      adminApi.get<WorkspaceSearchResponse>(
        `/api/v1/admin/workspaces${buildQueryString({ search, page_size: 20 })}`,
      ),
    staleTime: 30_000,
  });
}

export function useWorkspaceQuota(workspaceId: string | null) {
  return useQuery({
    queryKey: adminQueryKeys.workspaceQuota(workspaceId ?? "none"),
    queryFn: () =>
      adminApi.get<WorkspaceQuotaOverride>(
        `/api/v1/admin/settings/quotas/workspaces/${workspaceId}`,
      ),
    enabled: Boolean(workspaceId),
  });
}

export function useWorkspaceQuotaMutation(workspaceId: string | null) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (
      payload: VersionedMutationPayload<
        Omit<
          WorkspaceQuotaOverride,
          "updated_at" | "workspace_id" | "workspace_name"
        >
      >,
    ) => {
      if (!workspaceId) {
        throw new Error("Workspace is required");
      }

      return patchWithVersion<
        WorkspaceQuotaOverride,
        Omit<
          WorkspaceQuotaOverride,
          "updated_at" | "workspace_id" | "workspace_name"
        >
      >(`/api/v1/admin/settings/quotas/workspaces/${workspaceId}`, payload);
    },
    onSuccess: async () => {
      if (!workspaceId) {
        return;
      }

      await queryClient.invalidateQueries({
        queryKey: adminQueryKeys.workspaceQuota(workspaceId),
      });
    },
  });
}

export function useConnectorTypeConfigs() {
  return useQuery({
    queryKey: adminQueryKeys.connectorTypes(),
    queryFn: () =>
      adminApi.get<ConnectorTypeGlobalConfig[]>(
        "/api/v1/admin/settings/connectors",
      ),
  });
}

export function useConnectorTypeToggleMutation(typeSlug: string) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (is_enabled: boolean) =>
      adminApi.patch<ConnectorTypeGlobalConfig>(
        `/api/v1/admin/settings/connectors/${typeSlug}`,
        { is_enabled },
      ),
    onMutate: async (is_enabled) => {
      await queryClient.cancelQueries({
        queryKey: adminQueryKeys.connectorTypes(),
      });

      const previous = queryClient.getQueryData<ConnectorTypeGlobalConfig[]>(
        adminQueryKeys.connectorTypes(),
      );

      if (previous) {
        queryClient.setQueryData<ConnectorTypeGlobalConfig[]>(
          adminQueryKeys.connectorTypes(),
          previous.map((config) =>
            config.slug === typeSlug ? { ...config, is_enabled } : config,
          ),
        );
      }

      return { previous };
    },
    onError: (_error, _value, context) => {
      if (context?.previous) {
        queryClient.setQueryData(
          adminQueryKeys.connectorTypes(),
          context.previous,
        );
      }
    },
  });
}

export function useEmailConfig() {
  return useQuery({
    queryKey: adminQueryKeys.emailConfig(),
    queryFn: () =>
      adminApi.get<EmailDeliveryConfig>("/api/v1/admin/settings/email"),
  });
}

export function useEmailConfigMutation() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (
      payload: VersionedMutationPayload<Record<string, unknown>>,
    ) =>
      patchWithVersion<EmailDeliveryConfig, Record<string, unknown>>(
        "/api/v1/admin/settings/email",
        payload,
      ),
    onSuccess: async () => {
      await queryClient.invalidateQueries({
        queryKey: adminQueryKeys.emailConfig(),
      });
    },
  });
}

export function useSendTestEmailMutation() {
  return useMutation({
    mutationFn: (recipient: string) =>
      adminApi.post<TestEmailResult>("/api/v1/admin/settings/email/test", {
        recipient,
      }),
  });
}

export function useSecurityPolicy() {
  return useQuery({
    queryKey: adminQueryKeys.securityPolicy(),
    queryFn: () =>
      adminApi.get<SecurityPolicySettings>(
        "/api/v1/admin/settings/security",
      ),
  });
}

export function useSecurityPolicyMutation() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (
      payload: VersionedMutationPayload<Omit<SecurityPolicySettings, "updated_at">>,
    ) =>
      patchWithVersion<
        SecurityPolicySettings,
        Omit<SecurityPolicySettings, "updated_at">
      >("/api/v1/admin/settings/security", payload),
    onSuccess: async () => {
      await queryClient.invalidateQueries({
        queryKey: adminQueryKeys.securityPolicy(),
      });
    },
  });
}
