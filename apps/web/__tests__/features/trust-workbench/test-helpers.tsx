import type {
  CertificationDetail,
  CertificationListEntry,
  PrivacyImpactAnalysis,
  PolicyBinding,
  PolicySummary,
  TrustDimension,
  TrustRadarProfile,
} from "@/lib/types/trust-workbench";
import { useAuthStore } from "@/store/auth-store";
import { useWorkspaceStore } from "@/store/workspace-store";

export const sampleCertificationQueue: CertificationListEntry[] = [
  {
    id: "cert-1",
    agentId: "agent-1",
    agentFqn: "risk:fraud-monitor",
    agentRevisionId: "rev-1",
    entityName: "Fraud Monitor",
    entityFqn: "risk:fraud-monitor",
    entityType: "agent",
    certificationType: "behavioral_review",
    status: "pending",
    issuedBy: "trust-service",
    createdAt: "2026-04-16T08:00:00.000Z",
    updatedAt: "2026-04-16T08:30:00.000Z",
    expiresAt: "2026-05-01T00:00:00.000Z",
    revokedAt: null,
    revocationReason: null,
    evidenceCount: 3,
  },
  {
    id: "cert-2",
    agentId: "agent-2",
    agentFqn: "risk:kyc-review",
    agentRevisionId: "rev-2",
    entityName: "KYC Review",
    entityFqn: "risk:kyc-review",
    entityType: "agent",
    certificationType: "privacy_review",
    status: "active",
    issuedBy: "trust-service",
    createdAt: "2026-04-10T08:00:00.000Z",
    updatedAt: "2026-04-16T09:00:00.000Z",
    expiresAt: "2026-04-20T00:00:00.000Z",
    revokedAt: null,
    revocationReason: null,
    evidenceCount: 1,
  },
];

const primaryCertification = sampleCertificationQueue[0]!;

export const sampleCertificationDetail: CertificationDetail = {
  ...primaryCertification,
  supersededById: null,
  evidenceItems: [
    {
      id: "evidence-1",
      evidenceType: "package_validation",
      sourceRefType: "artifact",
      sourceRefId: "pkg-1",
      summary: "Pass: package checksum matched expected digest.",
      storageRef: JSON.stringify({ checksum: "abc123", validated: true }),
      createdAt: "2026-04-16T08:01:00.000Z",
      result: "pass",
    },
    {
      id: "evidence-2",
      evidenceType: "behavioral_regression",
      sourceRefType: "evaluation_run",
      sourceRefId: "eval-1",
      summary: "Partial alignment drift detected in 2 scenarios.",
      storageRef: null,
      createdAt: "2026-04-16T08:03:00.000Z",
      result: "partial",
    },
  ],
  statusHistory: [
    {
      id: "status-2",
      status: "pending",
      timestamp: "2026-04-16T08:30:00.000Z",
      actor: "trust.officer",
      notes: "Awaiting manual decision.",
    },
    {
      id: "status-1",
      status: "pending",
      timestamp: "2026-04-16T08:00:00.000Z",
      actor: "trust-service",
      notes: null,
    },
  ],
};

const trustDimensionOrder: TrustDimension[] = [
  "identity_auth",
  "authorization_access",
  "behavioral_compliance",
  "explainability",
  "evaluation_quality",
  "privacy_data",
  "certification_audit",
];

export const sampleTrustRadarProfile: TrustRadarProfile = {
  agentId: "agent-1",
  agentFqn: "risk:fraud-monitor",
  tier: "provisional",
  overallScore: 68,
  lastComputedAt: "2026-04-16T10:00:00.000Z",
  dimensions: trustDimensionOrder.map((dimension, index) => ({
    dimension,
    label: dimension,
    score: dimension === "behavioral_compliance" ? 22 : 70 + index,
    components: [
      {
        name: `${dimension}-component`,
        score: dimension === "behavioral_compliance" ? 22 : 70 + index,
        anomalyCount: dimension === "behavioral_compliance" ? 3 : undefined,
        trend: dimension === "behavioral_compliance" ? "down" : "stable",
      },
    ],
    isWeak: dimension === "behavioral_compliance",
  })),
};

export const samplePolicyCatalog: PolicySummary[] = [
  {
    id: "policy-direct",
    name: "Direct review guardrail",
    description: "Restricts high-risk escalations without manual approval.",
    scopeType: "agent",
    status: "active",
    workspaceId: "workspace-1",
    currentVersionId: "policy-direct-v1",
  },
  {
    id: "policy-new",
    name: "Fraud triage policy",
    description: "Applies enhanced triage enforcement for fraud workflows.",
    scopeType: "workspace",
    status: "active",
    workspaceId: "workspace-1",
    currentVersionId: "policy-new-v2",
  },
];

export const samplePolicyBindings: PolicyBinding[] = [
  {
    attachmentId: "attachment-direct",
    policyId: "policy-direct",
    policyVersionId: "policy-direct-v1",
    policyName: "Direct review guardrail",
    policyDescription: "Restricts high-risk escalations without manual approval.",
    scopeType: "agent",
    targetType: "agent_revision",
    targetId: "rev-1",
    isActive: true,
    createdAt: "2026-04-16T08:00:00.000Z",
    source: "direct",
    sourceLabel: "direct",
    sourceEntityUrl: null,
    canRemove: true,
  },
  {
    attachmentId: "attachment-fleet",
    policyId: "policy-inherited",
    policyVersionId: "policy-inherited-v1",
    policyName: "Fleet inherited policy",
    policyDescription: "Inherited from the fraud fleet.",
    scopeType: "fleet",
    targetType: "fleet",
    targetId: "fleet-1",
    isActive: true,
    createdAt: "2026-04-16T07:00:00.000Z",
    source: "fleet",
    sourceLabel: "fleet: Fraud Detection Fleet",
    sourceEntityUrl: "/fleet/fleet-1",
    canRemove: false,
  },
];

export const samplePrivacyAnalysis: PrivacyImpactAnalysis = {
  agentId: "agent-1",
  analysisTimestamp: "2026-04-16T08:00:00.000Z",
  overallCompliant: false,
  dataSources: ["evaluation_results", "behavioral_logs"],
  categories: [
    {
      name: "User PII",
      complianceStatus: "violation",
      retentionDuration: "45 days",
      concerns: [
        {
          description: "User email addresses exceed the approved retention window.",
          severity: "high",
        },
      ],
      recommendations: ["Reduce retention to 30 days and purge stale records."],
    },
    {
      name: "Behavioral logs",
      complianceStatus: "compliant",
      retentionDuration: "7 days",
      concerns: [],
      recommendations: [],
    },
  ],
};

export const sampleCompliantPrivacyAnalysis: PrivacyImpactAnalysis = {
  ...samplePrivacyAnalysis,
  overallCompliant: true,
  categories: [
    {
      name: "Behavioral logs",
      complianceStatus: "compliant",
      retentionDuration: "7 days",
      concerns: [],
      recommendations: [],
    },
  ],
};

export function seedTrustWorkbenchStores() {
  useAuthStore.setState({
    accessToken: "access-token",
    isAuthenticated: true,
    refreshToken: "refresh-token",
    user: {
      id: "user-1",
      email: "certifier@musematic.dev",
      displayName: "Trust Certifier",
      avatarUrl: null,
      mfaEnrolled: true,
      roles: ["trust_certifier", "platform_admin"],
      workspaceId: "workspace-1",
    },
  } as never);

  useWorkspaceStore.setState({
    currentWorkspace: {
      id: "workspace-1",
      name: "Risk Ops",
      slug: "risk-ops",
      description: "Trust workspace",
      memberCount: 10,
      createdAt: "2026-04-10T09:00:00.000Z",
    },
    isLoading: false,
    sidebarCollapsed: false,
    workspaceList: [],
  } as never);
}
