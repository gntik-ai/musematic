"use client";

import { createApiClient } from "@/lib/api";
import { useAppMutation, useAppQuery } from "@/lib/hooks/use-api";

export type PlanTier = "free" | "pro" | "enterprise";
export type AllowedModelTier = "cheap_only" | "standard" | "all";
export type QuotaPeriodAnchor = "calendar_month" | "subscription_anniversary";

export interface PlanVersionParameters {
  price_monthly: string;
  executions_per_day: number;
  executions_per_month: number;
  minutes_per_day: number;
  minutes_per_month: number;
  max_workspaces: number;
  max_agents_per_workspace: number;
  max_users_per_workspace: number;
  overage_price_per_minute: string;
  trial_days: number;
  quota_period_anchor: QuotaPeriodAnchor;
  extras?: Record<string, unknown>;
}

export interface PlanVersion extends PlanVersionParameters {
  id: string;
  plan_id: string;
  version: number;
  published_at: string | null;
  deprecated_at: string | null;
  created_at: string | null;
  created_by?: string | null;
  subscription_count?: number;
  diff_against_prior?: Record<string, { from: unknown; to: unknown }>;
}

export interface AdminPlan {
  id: string;
  slug: string;
  display_name: string;
  description?: string | null;
  tier: PlanTier;
  is_public: boolean;
  is_active: boolean;
  allowed_model_tier: AllowedModelTier;
  current_published_version: number | null;
  active_subscription_count: number;
  created_at: string | null;
  current_version?: PlanVersion | null;
  version_count?: number;
}

export interface PlanCreatePayload {
  slug: string;
  display_name: string;
  description?: string | null;
  tier: PlanTier;
  is_public: boolean;
  is_active?: boolean;
  allowed_model_tier: AllowedModelTier;
}

export interface PlanUpdatePayload {
  display_name?: string;
  description?: string | null;
  is_public?: boolean;
  is_active?: boolean;
}

export type PlanVersionPublishPayload = PlanVersionParameters;

interface PlanListResponse {
  items: AdminPlan[];
}

interface PlanVersionsResponse {
  items: PlanVersion[];
}

const adminPlansApi = createApiClient(
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000",
);

async function listPlans(): Promise<PlanListResponse> {
  return adminPlansApi.get<PlanListResponse>("/api/v1/admin/plans");
}

async function getPlan(slug: string): Promise<AdminPlan> {
  return adminPlansApi.get<AdminPlan>(`/api/v1/admin/plans/${slug}`);
}

async function getPlanVersions(slug: string): Promise<PlanVersionsResponse> {
  return adminPlansApi.get<PlanVersionsResponse>(`/api/v1/admin/plans/${slug}/versions`);
}

async function createPlan(payload: PlanCreatePayload): Promise<AdminPlan> {
  return adminPlansApi.post<AdminPlan>("/api/v1/admin/plans", payload, { skipRetry: true });
}

async function publishPlanVersion({
  slug,
  payload,
}: {
  slug: string;
  payload: PlanVersionPublishPayload;
}): Promise<PlanVersion> {
  return adminPlansApi.post<PlanVersion>(
    `/api/v1/admin/plans/${slug}/versions`,
    payload,
    { skipRetry: true },
  );
}

async function deprecatePlanVersion({
  slug,
  version,
}: {
  slug: string;
  version: number;
}): Promise<PlanVersion> {
  return adminPlansApi.post<PlanVersion>(
    `/api/v1/admin/plans/${slug}/versions/${version}/deprecate`,
    {},
    { skipRetry: true },
  );
}

async function updatePlanMetadata({
  slug,
  payload,
}: {
  slug: string;
  payload: PlanUpdatePayload;
}): Promise<AdminPlan> {
  return adminPlansApi.patch<AdminPlan>(
    `/api/v1/admin/plans/${slug}`,
    payload,
    { skipRetry: true },
  );
}

export function useAdminPlans() {
  return useAppQuery(["admin", "plans"], listPlans);
}

export function useAdminPlan(slug: string) {
  return useAppQuery(["admin", "plans", slug], () => getPlan(slug), {
    enabled: slug.length > 0,
  });
}

export function useAdminPlanVersions(slug: string) {
  return useAppQuery(["admin", "plans", slug, "versions"], () => getPlanVersions(slug), {
    enabled: slug.length > 0,
  });
}

export function useCreatePlan() {
  return useAppMutation(createPlan, {
    invalidateKeys: [["admin", "plans"]],
  });
}

export function usePublishPlanVersion() {
  return useAppMutation(publishPlanVersion, {
    invalidateKeys: [["admin", "plans"]],
  });
}

export function useDeprecatePlanVersion() {
  return useAppMutation(deprecatePlanVersion, {
    invalidateKeys: [["admin", "plans"]],
  });
}

export function useUpdatePlanMetadata() {
  return useAppMutation(updatePlanMetadata, {
    invalidateKeys: [["admin", "plans"]],
  });
}
