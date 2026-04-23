export type AlertTransitionType =
  | "execution.failed"
  | "execution.completed"
  | "interaction.idle"
  | "trust.certification_expired"
  | "trust.certification_expiring_soon"
  | "governance.verdict_issued"
  | "fleet.member_unhealthy"
  | "warm_pool.below_target";

export type AlertDeliveryMethod = "in-app" | "email" | "both";

export interface AlertRule {
  id: string;
  userId: string;
  workspaceId: string | null;
  transitionType: AlertTransitionType;
  enabled: boolean;
  deliveryMethod: AlertDeliveryMethod;
}

export interface InteractionAlertMute {
  interactionId: string;
  userId: string;
  mutedAt: string;
}

export interface Alert {
  id: string;
  transitionType: AlertTransitionType | string;
  resourceRef: { kind: string; id: string; url: string } | null;
  timestamp: string;
  read: boolean;
  title: string;
  summary: string;
}
