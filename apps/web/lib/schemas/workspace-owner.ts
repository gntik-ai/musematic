import { z } from "zod";

export const workspaceSummaryCardSchema = z.object({
  label: z.string(),
  value: z.union([z.string(), z.number()]),
  metadata: z.record(z.unknown()).default({}),
});

export const workspaceSummarySchema = z.object({
  workspace_id: z.string(),
  active_goals: z.number(),
  executions_in_flight: z.number(),
  agent_count: z.number(),
  budget: z.record(z.unknown()).default({}),
  quotas: z.record(z.unknown()).default({}),
  tags: z.record(z.unknown()).default({}),
  dlp_violations: z.number(),
  recent_activity: z.array(z.record(z.unknown())).default([]),
  cards: z.record(workspaceSummaryCardSchema).default({}),
  cached_until: z.string().nullable().optional(),
});

export const workspaceSettingsSchema = z.object({
  workspace_id: z.string(),
  subscribed_agents: z.array(z.string()).default([]),
  subscribed_fleets: z.array(z.string()).default([]),
  subscribed_policies: z.array(z.string()).default([]),
  subscribed_connectors: z.array(z.string()).default([]),
  cost_budget: z.record(z.unknown()).default({}),
  quota_config: z.record(z.unknown()).default({}),
  dlp_rules: z.record(z.unknown()).default({}),
  residency_config: z.record(z.unknown()).default({}),
  updated_at: z.string(),
});

export const workspaceMemberSchema = z.object({
  id: z.string(),
  workspace_id: z.string(),
  user_id: z.string(),
  role: z.enum(["owner", "admin", "member", "viewer"]),
  created_at: z.string(),
});

export const workspaceMembersResponseSchema = z.object({
  items: z.array(workspaceMemberSchema),
  total: z.number(),
  page: z.number(),
  page_size: z.number(),
  has_next: z.boolean(),
  has_prev: z.boolean(),
});

export const transferOwnershipChallengeSchema = z.object({
  challenge_id: z.string(),
  action_type: z.string(),
  status: z.string(),
  expires_at: z.string(),
});

export const challengeResponseSchema = z.object({
  id: z.string(),
  action_type: z.string(),
  status: z.string(),
  initiator_id: z.string(),
  co_signer_id: z.string().nullable().optional(),
  created_at: z.string(),
  expires_at: z.string(),
  approved_at: z.string().nullable().optional(),
  consumed_at: z.string().nullable().optional(),
});

export const consumeChallengeResponseSchema = z.object({
  id: z.string(),
  action_type: z.string(),
  status: z.string(),
  action_result: z.record(z.unknown()).default({}),
});

export const connectorInstanceSchema = z.object({
  id: z.string(),
  workspace_id: z.string(),
  connector_type_id: z.string(),
  connector_type_slug: z.string(),
  name: z.string(),
  config: z.record(z.unknown()).default({}),
  status: z.string(),
  health_status: z.string(),
  last_health_check_at: z.string().nullable().optional(),
  health_check_error: z.string().nullable().optional(),
  messages_sent: z.number().default(0),
  messages_failed: z.number().default(0),
  messages_retried: z.number().default(0),
  messages_dead_lettered: z.number().default(0),
  credential_keys: z.array(z.string()).default([]),
  created_at: z.string(),
  updated_at: z.string(),
});

export const connectorInstanceListSchema = z.object({
  items: z.array(connectorInstanceSchema),
  total: z.number(),
});

export const connectorDeliverySchema = z.object({
  id: z.string(),
  workspace_id: z.string(),
  connector_instance_id: z.string(),
  destination: z.string(),
  status: z.string(),
  attempt_count: z.number(),
  max_attempts: z.number(),
  delivered_at: z.string().nullable().optional(),
  error_history: z.array(z.record(z.unknown())).default([]),
  created_at: z.string(),
  updated_at: z.string(),
});

export const connectorDeliveryListSchema = z.object({
  items: z.array(connectorDeliverySchema),
  total: z.number(),
});

export const testConnectivityResponseSchema = z.object({
  connector_instance_id: z.string(),
  connector_type_slug: z.string(),
  result: z.object({
    success: z.boolean(),
    diagnostic: z.string(),
    latency_ms: z.number(),
  }),
});

export const visibilityGrantSchema = z.object({
  workspace_id: z.string(),
  visibility_agents: z.array(z.string()).default([]),
  visibility_tools: z.array(z.string()).default([]),
  updated_at: z.string(),
});

export const stepResultSchema = z.object({
  step: z.string(),
  status: z.string(),
  duration_ms: z.number(),
  error: z.string().nullable().optional(),
});

export const testConnectionResponseSchema = z.object({
  connector_id: z.string(),
  steps: z.array(stepResultSchema),
  success: z.boolean(),
});

export const iborSyncRunSchema = z.object({
  id: z.string(),
  connector_id: z.string(),
  mode: z.string(),
  started_at: z.string(),
  finished_at: z.string().nullable().optional(),
  status: z.string(),
  counts: z.record(z.number()).default({}),
  error_details: z.array(z.record(z.unknown())).default([]),
  triggered_by: z.string().nullable().optional(),
});

export const iborSyncHistorySchema = z.object({
  items: z.array(iborSyncRunSchema),
  next_cursor: z.string().nullable().optional(),
});

export const iborConnectorSchema = z.object({
  id: z.string(),
  name: z.string(),
  source_type: z.string(),
  sync_mode: z.string(),
  cadence_seconds: z.number(),
  credential_ref: z.string(),
  role_mapping_policy: z.array(z.record(z.unknown())).default([]),
  enabled: z.boolean(),
  last_run_at: z.string().nullable().optional(),
  last_run_status: z.string().nullable().optional(),
  created_by: z.string(),
  created_at: z.string(),
  updated_at: z.string(),
});

export const iborConnectorListSchema = z.object({
  items: z.array(iborConnectorSchema),
});

export const iborConnectorCreateSchema = z.object({
  name: z.string().min(1),
  source_type: z.enum(["ldap", "oidc", "scim"]),
  sync_mode: z.enum(["pull", "push"]),
  cadence_seconds: z.number().int().min(60).max(86_400),
  credential_ref: z.string().min(1),
  role_mapping_policy: z
    .array(
      z.object({
        directory_group: z.string().min(1),
        platform_role: z.string().min(1),
        workspace_scope: z.string().nullable().optional(),
      }),
    )
    .default([]),
  enabled: z.boolean(),
});

export type WorkspaceSummary = z.infer<typeof workspaceSummarySchema>;
export type WorkspaceSettings = z.infer<typeof workspaceSettingsSchema>;
export type WorkspaceMember = z.infer<typeof workspaceMemberSchema>;
export type WorkspaceMembersResponse = z.infer<typeof workspaceMembersResponseSchema>;
export type TransferOwnershipChallenge = z.infer<typeof transferOwnershipChallengeSchema>;
export type ChallengeResponse = z.infer<typeof challengeResponseSchema>;
export type ConsumeChallengeResponse = z.infer<typeof consumeChallengeResponseSchema>;
export type ConnectorInstance = z.infer<typeof connectorInstanceSchema>;
export type ConnectorDelivery = z.infer<typeof connectorDeliverySchema>;
export type TestConnectivityResponse = z.infer<typeof testConnectivityResponseSchema>;
export type VisibilityGrant = z.infer<typeof visibilityGrantSchema>;
export type TestConnectionResponse = z.infer<typeof testConnectionResponseSchema>;
export type IBORSyncHistory = z.infer<typeof iborSyncHistorySchema>;
export type IBORConnector = z.infer<typeof iborConnectorSchema>;
export type IBORConnectorCreate = z.infer<typeof iborConnectorCreateSchema>;
