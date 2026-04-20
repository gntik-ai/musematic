"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import {
  normalizeInteractionAlertMutes,
  serializeInteractionAlertMutes,
  writeInteractionAlertMutes,
} from "@/lib/alerts/interaction-mutes";
import { createApiClient } from "@/lib/api";
import { useAppQuery } from "@/lib/hooks/use-api";
import { ApiError } from "@/types/api";
import type {
  AlertDeliveryMethod,
  AlertRule,
  AlertTransitionType,
  InteractionAlertMute,
} from "@/types/alerts";

const api = createApiClient(
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000",
);

export const ALERT_TRANSITIONS: AlertTransitionType[] = [
  "execution.failed",
  "execution.completed",
  "interaction.idle",
  "trust.certification_expired",
  "trust.certification_expiring_soon",
  "governance.verdict_issued",
  "fleet.member_unhealthy",
  "warm_pool.below_target",
];

interface AlertSettingsRead {
  id: string;
  user_id: string;
  state_transitions: string[];
  delivery_method: "in_app" | "email" | "webhook";
  interaction_mutes?: Array<{
    interaction_id: string;
    muted_at: string;
    user_id?: string;
  }>;
}

function normalizeDeliveryMethod(
  value: AlertSettingsRead["delivery_method"],
): AlertDeliveryMethod {
  switch (value) {
    case "email":
      return "email";
    default:
      return "in-app";
  }
}

function serializeDeliveryMethod(
  value: AlertDeliveryMethod,
): AlertSettingsRead["delivery_method"] {
  switch (value) {
    case "email":
    case "both":
      return "email";
    default:
      return "in_app";
  }
}

function toRules(
  payload: AlertSettingsRead,
  workspaceId: string | null | undefined,
): AlertRule[] {
  return ALERT_TRANSITIONS.map((transition) => ({
    id: `${payload.id}:${transition}`,
    userId: payload.user_id,
    workspaceId: workspaceId ?? null,
    transitionType: transition,
    enabled: payload.state_transitions.includes(transition),
    deliveryMethod: normalizeDeliveryMethod(payload.delivery_method),
  }));
}

export function useAlertRules(
  userId: string | null | undefined,
  workspaceId: string | null | undefined,
) {
  const query = useAppQuery<{
    interactionMutes: InteractionAlertMute[];
    rules: AlertRule[];
    settings: AlertSettingsRead;
  }>(
    ["alert-rules", userId ?? "none", workspaceId ?? "global"],
    async () => {
      const settings = await api.get<AlertSettingsRead>("/me/alert-settings");
      return {
        interactionMutes: normalizeInteractionAlertMutes(
          settings.interaction_mutes,
          userId,
        ),
        rules: toRules(settings, workspaceId),
        settings,
      };
    },
    { enabled: Boolean(userId), staleTime: 60_000 },
  );

  return {
    ...query,
    interactionMutes:
      query.data?.interactionMutes ??
      normalizeInteractionAlertMutes(undefined, userId),
    rules: query.data?.rules ?? [],
    settings: query.data?.settings ?? null,
  };
}

export function useAlertRulesMutations(
  userId: string | null | undefined,
) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async ({
      deliveryMethod,
      interactionMutes,
      transitionTypes,
    }: {
      deliveryMethod: AlertDeliveryMethod;
      interactionMutes?: InteractionAlertMute[];
      transitionTypes: string[];
    }) => {
      const basePayload = {
        delivery_method: serializeDeliveryMethod(deliveryMethod),
        state_transitions: transitionTypes,
      };
      const normalizedInteractionMutes =
        interactionMutes ?? normalizeInteractionAlertMutes(undefined, userId);

      try {
        const response = await api.put<AlertSettingsRead>(
          "/me/alert-settings",
          interactionMutes === undefined
            ? basePayload
            : {
                ...basePayload,
                interaction_mutes:
                  serializeInteractionAlertMutes(normalizedInteractionMutes),
              },
        );

        if (interactionMutes !== undefined) {
          writeInteractionAlertMutes(userId, normalizedInteractionMutes);
        }

        return response;
      } catch (error) {
        if (
          interactionMutes !== undefined &&
          error instanceof ApiError &&
          (error.status === 400 || error.status === 422)
        ) {
          const response = await api.put<AlertSettingsRead>(
            "/me/alert-settings",
            basePayload,
          );
          writeInteractionAlertMutes(userId, normalizedInteractionMutes);
          return response;
        }

        throw error;
      }
    },
    onSuccess: async () => {
      await queryClient.invalidateQueries({
        queryKey: ["alert-rules", userId ?? "none"],
      });
    },
  });
}
