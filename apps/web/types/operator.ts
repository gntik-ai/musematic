export interface WarmPoolProfile {
  name: "small" | "medium" | "large" | string;
  targetReplicas: number;
  actualReplicas: number;
  deltaStatus: "on_target" | "within_20_percent" | "below_target";
  lastScalingEvents: Array<{
    at: string;
    from: number;
    to: number;
    reason: string;
  }>;
}

export interface DecommissionPlan {
  agentFqn: string;
  dependencies: string[];
  dryRunSummary: string[];
}

export interface ReliabilityGauge {
  id: "api" | "execution" | "event_delivery" | string;
  availabilityPercent: number;
  windowDays: number;
}

export interface ThirdPartyCertifier {
  id: string;
  displayName: string;
  endpoint: string;
  scope: string[];
  publicKeyFingerprint: string | null;
}

export interface SurveillanceSignal {
  id: string;
  agentId: string;
  signalType: string;
  score: number;
  timestamp: string;
  summary: string;
}
