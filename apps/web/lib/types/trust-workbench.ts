"use client";

export type CertificationStatus =
  | "pending"
  | "active"
  | "expired"
  | "revoked"
  | "superseded";

export type CertificationQueueStatus = "pending" | "expiring" | "revoked";

export type CertificationQueueSortField = "expiration" | "urgency" | "created";

export type CertificationEntityType = "agent" | "fleet";

export type EvidenceType =
  | "package_validation"
  | "test_results"
  | "policy_check"
  | "guardrail_outcomes"
  | "behavioral_regression"
  | "ate_results"
  | "manual_review";

export type EvidenceResult = "pass" | "fail" | "partial" | "unknown";

export type TrustTierName = "certified" | "provisional" | "untrusted";

export type TrustDimension =
  | "identity_auth"
  | "authorization_access"
  | "behavioral_compliance"
  | "explainability"
  | "evaluation_quality"
  | "privacy_data"
  | "certification_audit";

export const TRUST_DIMENSION_LABELS: Record<TrustDimension, string> = {
  identity_auth: "Identity & Authentication",
  authorization_access: "Authorization & Access Control",
  behavioral_compliance: "Behavioral Compliance",
  explainability: "Explainability",
  evaluation_quality: "Evaluation Quality",
  privacy_data: "Privacy & Data Protection",
  certification_audit: "Certification & Audit Trail",
};

export const CERTIFICATION_STATUS_LABELS: Record<
  CertificationStatus | "expiring",
  string
> = {
  pending: "Pending",
  active: "Active",
  expiring: "Expiring",
  expired: "Expired",
  revoked: "Revoked",
  superseded: "Superseded",
};

export const CERTIFICATION_QUEUE_STATUS_LABELS: Record<
  CertificationQueueStatus | "all",
  string
> = {
  all: "All",
  pending: "Pending",
  expiring: "Expiring",
  revoked: "Revoked",
};

export const EVIDENCE_TYPE_LABELS: Record<EvidenceType, string> = {
  package_validation: "Package validation",
  test_results: "Test results",
  policy_check: "Policy check",
  guardrail_outcomes: "Guardrail outcomes",
  behavioral_regression: "Behavioral regression",
  ate_results: "ATE results",
  manual_review: "Manual review",
};

export type PolicyScopeType =
  | "global"
  | "deployment"
  | "workspace"
  | "agent"
  | "fleet"
  | "execution";

export type AttachmentTargetType =
  | "global"
  | "deployment"
  | "workspace"
  | "agent_revision"
  | "fleet"
  | "execution";

export type PolicyBindingSource =
  | "direct"
  | "workspace"
  | "fleet"
  | "global"
  | "deployment";

export type PrivacyComplianceStatus = "compliant" | "warning" | "violation";

export type TrustWorkbenchDetailTab =
  | "evidence"
  | "trust-radar"
  | "policies"
  | "privacy";

export const TRUST_WORKBENCH_PAGE_SIZES = [20, 50, 100] as const;

export const TRUST_WORKBENCH_TABS: TrustWorkbenchDetailTab[] = [
  "evidence",
  "trust-radar",
  "policies",
  "privacy",
];

export interface TrustRadarChartDataPoint {
  subject: string;
  score: number;
  fullMark: 100;
  dimension: TrustDimension;
  isWeak: boolean;
}

export interface CertificationListEntry {
  id: string;
  agentId: string;
  agentFqn: string;
  agentRevisionId: string;
  entityName: string;
  entityFqn: string;
  entityType: CertificationEntityType;
  certificationType: string;
  status: CertificationStatus;
  issuedBy: string;
  createdAt: string;
  updatedAt: string;
  expiresAt: string | null;
  revokedAt: string | null;
  revocationReason: string | null;
  evidenceCount: number;
  fleetId?: string | undefined;
  fleetName?: string | undefined;
}

export interface CertificationDetail extends CertificationListEntry {
  supersededById: string | null;
  evidenceItems: EvidenceItem[];
  statusHistory: CertificationStatusEvent[];
}

export interface CertificationStatusEvent {
  id: string;
  status: CertificationStatus;
  timestamp: string;
  actor: string;
  notes: string | null;
}

export interface EvidenceItem {
  id: string;
  evidenceType: EvidenceType;
  sourceRefType: string;
  sourceRefId: string;
  summary: string | null;
  storageRef: string | null;
  createdAt: string;
  result: EvidenceResult;
}

export interface TrustDimensionComponent {
  name: string;
  score: number;
  anomalyCount?: number | undefined;
  trend?: "up" | "down" | "stable" | undefined;
}

export interface TrustDimensionScore {
  dimension: TrustDimension;
  label: string;
  score: number;
  components: TrustDimensionComponent[];
  isWeak: boolean;
}

export interface TrustRadarProfile {
  agentId: string;
  agentFqn: string;
  tier: TrustTierName;
  overallScore: number;
  dimensions: TrustDimensionScore[];
  lastComputedAt: string;
  isFleetAggregate?: boolean;
  memberCount?: number;
}

export interface PolicySummary {
  id: string;
  name: string;
  description: string | null;
  scopeType: PolicyScopeType;
  status: "active" | "archived" | "suspended";
  workspaceId: string | null;
  currentVersionId: string | null;
}

export interface PolicyBinding {
  attachmentId: string;
  policyId: string;
  policyVersionId: string;
  policyName: string;
  policyDescription: string | null;
  scopeType: PolicyScopeType;
  targetType: AttachmentTargetType;
  targetId: string | null;
  isActive: boolean;
  createdAt: string;
  source: PolicyBindingSource;
  sourceLabel: string | null;
  sourceEntityUrl: string | null;
  canRemove: boolean;
}

export interface PolicyRuleProvenance {
  ruleId: string;
  policyId: string;
  versionId: string;
  scopeLevel: number;
  scopeType: PolicyScopeType;
  scopeTargetId: string | null;
}

export interface PolicyConflict {
  ruleId: string;
  winnerScope: PolicyScopeType;
  loserScope: PolicyScopeType;
  resolution: "more_specific_scope_wins" | "deny_wins";
}

export interface PrivacyImpactAnalysis {
  agentId: string;
  analysisTimestamp: string;
  overallCompliant: boolean;
  dataSources: string[];
  categories: PrivacyDataCategory[];
}

export interface PrivacyDataCategory {
  name: string;
  complianceStatus: PrivacyComplianceStatus;
  retentionDuration: string | null;
  concerns: PrivacyConcern[];
  recommendations: string[];
}

export interface PrivacyConcern {
  description: string;
  severity: "low" | "medium" | "high";
}

export interface ReviewDecisionFormValues {
  decision: "approve" | "reject";
  notes: string;
  supportingFiles: File[];
}

export interface CertificationQueueFilters {
  status: CertificationQueueStatus | null;
  search: string;
  tags: string[];
  labels: Record<string, string>;
  sort_by: CertificationQueueSortField;
  page: number;
  page_size: (typeof TRUST_WORKBENCH_PAGE_SIZES)[number];
}

export const DEFAULT_CERTIFICATION_QUEUE_FILTERS: CertificationQueueFilters = {
  status: null,
  search: "",
  tags: [],
  labels: {},
  sort_by: "expiration",
  page: 1,
  page_size: 20,
};

export function isTrustWorkbenchDetailTab(
  value: string | null | undefined,
): value is TrustWorkbenchDetailTab {
  return TRUST_WORKBENCH_TABS.includes(
    (value ?? "") as TrustWorkbenchDetailTab,
  );
}

export function buildTrustWorkbenchDetailHref(
  certificationId: string,
  tab?: TrustWorkbenchDetailTab,
): string {
  const pathname = `/trust-workbench/${encodeURIComponent(certificationId)}`;
  if (!tab || tab === "evidence") {
    return pathname;
  }

  const params = new URLSearchParams({ tab });
  return `${pathname}?${params.toString()}`;
}

export function toTrustRadarChartData(
  profile: TrustRadarProfile,
): TrustRadarChartDataPoint[] {
  return profile.dimensions.map((dimension) => ({
    subject: dimension.label,
    score: dimension.score,
    fullMark: 100,
    dimension: dimension.dimension,
    isWeak: dimension.isWeak,
  }));
}
