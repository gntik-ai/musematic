"use client";

import { createApiClient } from "@/lib/api";
import type {
  ChallengeResponse,
  ConnectorDelivery,
  ConnectorInstance,
  ConsumeChallengeResponse,
  IBORConnector,
  IBORConnectorCreate,
  IBORSyncHistory,
  TestConnectionResponse,
  TestConnectivityResponse,
  TransferOwnershipChallenge,
  VisibilityGrant,
  WorkspaceMember,
  WorkspaceMembersResponse,
  WorkspaceSettings,
  WorkspaceSummary,
} from "@/lib/schemas/workspace-owner";
import type { PaginatedResponse } from "@/types/api";
import type { Workspace } from "@/types/workspace";

const api = createApiClient(process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000");

export interface ConnectorListResponse {
  items: ConnectorInstance[];
  total: number;
}

export interface ConnectorDeliveryListResponse {
  items: ConnectorDelivery[];
  total: number;
}

export async function listWorkspaces(): Promise<PaginatedResponse<Workspace> | { items: Workspace[] }> {
  return api.get<PaginatedResponse<Workspace> | { items: Workspace[] }>("/api/v1/workspaces");
}

export async function getWorkspaceSummary(workspaceId: string): Promise<WorkspaceSummary> {
  return api.get<WorkspaceSummary>(`/api/v1/workspaces/${workspaceId}/summary`);
}

export async function getWorkspaceSettings(workspaceId: string): Promise<WorkspaceSettings> {
  return api.get<WorkspaceSettings>(`/api/v1/workspaces/${workspaceId}/settings`);
}

export async function updateWorkspaceSettings(
  workspaceId: string,
  payload: Partial<Pick<
    WorkspaceSettings,
    "cost_budget" | "quota_config" | "dlp_rules" | "residency_config"
  >>,
): Promise<WorkspaceSettings> {
  return api.patch<WorkspaceSettings>(`/api/v1/workspaces/${workspaceId}/settings`, payload);
}

export async function listWorkspaceMembers(
  workspaceId: string,
  page = 1,
): Promise<WorkspaceMembersResponse> {
  return api.get<WorkspaceMembersResponse>(
    `/api/v1/workspaces/${workspaceId}/members?page=${page}&page_size=50`,
  );
}

export async function inviteWorkspaceMember(
  workspaceId: string,
  payload: { user_id: string; role: WorkspaceMember["role"] },
): Promise<WorkspaceMember> {
  return api.post<WorkspaceMember>(`/api/v1/workspaces/${workspaceId}/members`, payload);
}

export async function updateWorkspaceMemberRole(
  workspaceId: string,
  userId: string,
  payload: { role: WorkspaceMember["role"] },
): Promise<WorkspaceMember> {
  return api.patch<WorkspaceMember>(`/api/v1/workspaces/${workspaceId}/members/${userId}`, payload);
}

export async function removeWorkspaceMember(workspaceId: string, userId: string): Promise<void> {
  return api.delete<void>(`/api/v1/workspaces/${workspaceId}/members/${userId}`);
}

export async function transferWorkspaceOwnership(
  workspaceId: string,
  newOwnerId: string,
): Promise<TransferOwnershipChallenge> {
  return api.post<TransferOwnershipChallenge>(
    `/api/v1/workspaces/${workspaceId}/transfer-ownership`,
    { new_owner_id: newOwnerId },
  );
}

export async function getChallenge(challengeId: string): Promise<ChallengeResponse> {
  return api.get<ChallengeResponse>(`/api/v1/2pa/challenges/${challengeId}`);
}

export async function createChallenge(payload: {
  action_type: string;
  action_payload: Record<string, unknown>;
  ttl_seconds?: number;
}): Promise<ChallengeResponse> {
  return api.post<ChallengeResponse>("/api/v1/2pa/challenges", payload);
}

export async function approveChallenge(challengeId: string): Promise<ChallengeResponse> {
  return api.post<ChallengeResponse>(`/api/v1/2pa/challenges/${challengeId}/approve`);
}

export async function consumeChallenge(challengeId: string): Promise<ConsumeChallengeResponse> {
  return api.post<ConsumeChallengeResponse>(`/api/v1/2pa/challenges/${challengeId}/consume`);
}

export async function listWorkspaceConnectors(workspaceId: string): Promise<ConnectorListResponse> {
  return api.get<ConnectorListResponse>(`/api/v1/workspaces/${workspaceId}/connectors`);
}

export async function getWorkspaceConnector(
  workspaceId: string,
  connectorId: string,
): Promise<ConnectorInstance> {
  return api.get<ConnectorInstance>(`/api/v1/workspaces/${workspaceId}/connectors/${connectorId}`);
}

export async function testConnectorConnectivity(
  workspaceId: string,
  connectorId: string,
  payload: { config?: Record<string, unknown>; credential_refs?: Record<string, string> },
): Promise<TestConnectivityResponse> {
  return api.post<TestConnectivityResponse>(
    `/api/v1/workspaces/${workspaceId}/connectors/${connectorId}/test-connectivity`,
    payload,
  );
}

export async function listConnectorDeliveries(
  workspaceId: string,
  connectorId: string,
): Promise<ConnectorDeliveryListResponse> {
  return api.get<ConnectorDeliveryListResponse>(
    `/api/v1/workspaces/${workspaceId}/deliveries?connector_instance_id=${connectorId}`,
  );
}

export async function getVisibilityGrant(workspaceId: string): Promise<VisibilityGrant> {
  return api.get<VisibilityGrant>(`/api/v1/workspaces/${workspaceId}/visibility`);
}

export async function listIBORConnectors(): Promise<{ items: IBORConnector[] }> {
  return api.get<{ items: IBORConnector[] }>("/api/v1/auth/ibor/connectors");
}

export async function createIBORConnector(payload: IBORConnectorCreate): Promise<IBORConnector> {
  return api.post<IBORConnector>("/api/v1/auth/ibor/connectors", payload);
}

export async function testIBORConnection(connectorId: string): Promise<TestConnectionResponse> {
  return api.post<TestConnectionResponse>(`/api/v1/auth/ibor/connectors/${connectorId}/test-connection`);
}

export async function syncIBORNow(connectorId: string): Promise<unknown> {
  return api.post<unknown>(`/api/v1/auth/ibor/connectors/${connectorId}/sync-now`);
}

export async function getIBORSyncHistory(
  connectorId: string,
  cursor?: string | null,
): Promise<IBORSyncHistory> {
  const query = cursor ? `?cursor=${encodeURIComponent(cursor)}` : "";
  return api.get<IBORSyncHistory>(
    `/api/v1/auth/ibor/connectors/${connectorId}/sync-history${query}`,
  );
}
