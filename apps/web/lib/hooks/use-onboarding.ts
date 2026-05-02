"use client";

import { createApiClient } from "@/lib/api";
import { useAppMutation, useAppQuery } from "@/lib/hooks/use-api";

const onboardingApi = createApiClient(
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000",
);

export type OnboardingStep = "workspace_named" | "invitations" | "first_agent" | "tour" | "done";

export interface OnboardingState {
  id: string;
  user_id: string;
  tenant_id: string;
  step_workspace_named: boolean;
  step_invitations_sent_or_skipped: boolean;
  step_first_agent_created_or_skipped: boolean;
  step_tour_started_or_skipped: boolean;
  last_step_attempted: OnboardingStep;
  dismissed_at: string | null;
  first_agent_step_available: boolean;
  default_workspace_id: string | null;
  default_workspace_name: string | null;
}

export interface OnboardingWorkspaceNamePayload {
  workspace_name: string;
}

export interface OnboardingInvitationsPayload {
  invitations: Array<{
    email: string;
    role?: string;
    message?: string | null;
  }>;
}

export interface OnboardingFirstAgentPayload {
  agent_id?: string | null;
  skipped?: boolean;
}

export interface OnboardingTourPayload {
  started?: boolean;
  skipped?: boolean;
}

export const onboardingQueryKeys = {
  state: ["onboarding", "state"] as const,
};

export function useOnboarding() {
  const state = useAppQuery(onboardingQueryKeys.state, getOnboardingState);
  const invalidateKeys = [onboardingQueryKeys.state];

  return {
    state,
    dismiss: useAppMutation(dismissOnboarding, { invalidateKeys }),
    firstAgent: useAppMutation(submitFirstAgent, { invalidateKeys }),
    invitations: useAppMutation(submitInvitations, { invalidateKeys }),
    relaunch: useAppMutation(relaunchOnboarding, { invalidateKeys }),
    tour: useAppMutation(submitTour, { invalidateKeys }),
    workspaceName: useAppMutation(submitWorkspaceName, { invalidateKeys }),
  };
}

async function getOnboardingState(): Promise<OnboardingState> {
  return onboardingApi.get<OnboardingState>("/api/v1/onboarding/state");
}

async function submitWorkspaceName(
  payload: OnboardingWorkspaceNamePayload,
): Promise<OnboardingState> {
  return onboardingApi.post<OnboardingState>("/api/v1/onboarding/step/workspace-name", payload);
}

async function submitInvitations(
  payload: OnboardingInvitationsPayload,
): Promise<OnboardingState> {
  return onboardingApi.post<OnboardingState>("/api/v1/onboarding/step/invitations", payload);
}

async function submitFirstAgent(
  payload: OnboardingFirstAgentPayload,
): Promise<OnboardingState> {
  return onboardingApi.post<OnboardingState>("/api/v1/onboarding/step/first-agent", payload);
}

async function submitTour(payload: OnboardingTourPayload): Promise<OnboardingState> {
  return onboardingApi.post<OnboardingState>("/api/v1/onboarding/step/tour", payload);
}

async function dismissOnboarding(): Promise<OnboardingState> {
  return onboardingApi.post<OnboardingState>("/api/v1/onboarding/dismiss");
}

async function relaunchOnboarding(): Promise<OnboardingState> {
  return onboardingApi.post<OnboardingState>("/api/v1/onboarding/relaunch");
}
