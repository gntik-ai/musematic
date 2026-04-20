"use client";

import { Bell, BellOff } from "lucide-react";
import {
  removeInteractionAlertMute,
  upsertInteractionAlertMute,
} from "@/lib/alerts/interaction-mutes";
import { useAlertRules, useAlertRulesMutations } from "@/lib/hooks/use-alert-rules";
import { useAuthStore } from "@/store/auth-store";
import { useWorkspaceStore } from "@/store/workspace-store";
import { Toggle } from "@/components/ui/toggle";

export interface PerInteractionMuteToggleProps {
  interactionId: string;
}

export function PerInteractionMuteToggle({
  interactionId,
}: PerInteractionMuteToggleProps) {
  const userId = useAuthStore((state) => state.user?.id ?? null);
  const workspaceId = useWorkspaceStore((state) => state.currentWorkspace?.id ?? null);
  const { interactionMutes, isLoading, rules } = useAlertRules(userId, workspaceId);
  const mutation = useAlertRulesMutations(userId);

  const isMuted = interactionMutes.some(
    (mute) => mute.interactionId === interactionId,
  );
  const enabledTransitions = rules
    .filter((rule) => rule.enabled)
    .map((rule) => rule.transitionType);
  const deliveryMethod = rules[0]?.deliveryMethod ?? "in-app";
  const isDisabled = !userId || isLoading || mutation.isPending || rules.length === 0;

  return (
    <Toggle
      aria-label={
        isMuted
          ? "Alerts muted for this interaction"
          : "Mute alerts for this interaction"
      }
      className="rounded-full"
      disabled={isDisabled}
      onPressedChange={(nextPressed) => {
        if (!userId) {
          return;
        }

        mutation.mutate({
          deliveryMethod,
          interactionMutes: nextPressed
            ? upsertInteractionAlertMute(interactionMutes, interactionId, userId)
            : removeInteractionAlertMute(interactionMutes, interactionId),
          transitionTypes: enabledTransitions,
        });
      }}
      pressed={isMuted}
      size="sm"
      title={
        isMuted
          ? "Alerts muted for this interaction"
          : "Mute alerts for this interaction"
      }
      type="button"
    >
      {isMuted ? <BellOff className="h-3.5 w-3.5" /> : <Bell className="h-3.5 w-3.5" />}
      <span className="hidden sm:inline">
        {isMuted ? "Alerts muted" : "Mute alerts"}
      </span>
    </Toggle>
  );
}
