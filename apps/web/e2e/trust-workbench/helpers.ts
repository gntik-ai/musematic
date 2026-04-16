import type { Page } from "@playwright/test";

type CertificationQueueFixture = {
  id: string;
  agent_id: string;
  agent_fqn: string;
  agent_revision_id: string;
  entity_name: string;
  entity_fqn: string;
  entity_type: "agent" | "fleet";
  certification_type: string;
  status: "pending" | "active" | "revoked";
  issued_by: string;
  created_at: string;
  updated_at: string;
  expires_at: string | null;
  evidence_count: number;
  revocation_reason?: string | undefined;
};

const certificationQueue: CertificationQueueFixture[] = [
  {
    id: "cert-1",
    agent_id: "agent-1",
    agent_fqn: "risk:fraud-monitor",
    agent_revision_id: "rev-1",
    entity_name: "Fraud Monitor",
    entity_fqn: "risk:fraud-monitor",
    entity_type: "agent",
    certification_type: "behavioral_review",
    status: "pending",
    issued_by: "trust-service",
    created_at: "2026-04-16T08:00:00.000Z",
    updated_at: "2026-04-16T08:30:00.000Z",
    expires_at: "2026-05-01T00:00:00.000Z",
    evidence_count: 2,
  },
  {
    id: "cert-2",
    agent_id: "agent-2",
    agent_fqn: "risk:kyc-review",
    agent_revision_id: "rev-2",
    entity_name: "KYC Review",
    entity_fqn: "risk:kyc-review",
    entity_type: "agent",
    certification_type: "privacy_review",
    status: "pending",
    issued_by: "trust-service",
    created_at: "2026-04-15T08:00:00.000Z",
    updated_at: "2026-04-15T08:30:00.000Z",
    expires_at: "2026-04-25T00:00:00.000Z",
    evidence_count: 1,
  },
  {
    id: "cert-3",
    agent_id: "agent-3",
    agent_fqn: "risk:revoked-agent",
    agent_revision_id: "rev-3",
    entity_name: "Revoked Agent",
    entity_fqn: "risk:revoked-agent",
    entity_type: "agent",
    certification_type: "policy_review",
    status: "revoked",
    issued_by: "trust-service",
    created_at: "2026-04-10T08:00:00.000Z",
    updated_at: "2026-04-12T08:30:00.000Z",
    expires_at: null,
    evidence_count: 3,
    revocation_reason: "Policy breach",
  },
];

export async function installTrustWorkbenchState(page: Page) {
  await page.addInitScript(() => {
    localStorage.setItem(
      "auth-storage",
      JSON.stringify({
        state: {
          user: {
            id: "user-1",
            email: "certifier@musematic.dev",
            displayName: "Trust Certifier",
            avatarUrl: null,
            roles: ["trust_certifier", "platform_admin"],
            workspaceId: "workspace-1",
            mfaEnrolled: true,
          },
          accessToken: "mock-access-token",
          refreshToken: "mock-refresh-token",
          isAuthenticated: true,
          isLoading: false,
        },
        version: 0,
      }),
    );

    localStorage.setItem(
      "workspace-storage",
      JSON.stringify({
        state: {
          currentWorkspace: {
            id: "workspace-1",
            name: "Risk Ops",
            slug: "risk-ops",
            description: "Primary trust workspace",
            memberCount: 8,
            createdAt: "2026-04-10T09:00:00.000Z",
          },
          sidebarCollapsed: false,
        },
        version: 0,
      }),
    );
  });
}

function matchSearch(text: string, search: string): boolean {
  const term = search.trim().toLowerCase();
  if (!term) {
    return true;
  }

  return text.toLowerCase().includes(term);
}

function buildDetailRecord(
  id: string,
  status: "pending" | "active" | "revoked",
  notes: string | null,
) {
  const queueEntry = certificationQueue.find((entry) => entry.id === id)!;

  return {
    ...queueEntry,
    status,
    evidence_refs: [
      {
        id: `${id}-evidence-1`,
        evidence_type: "package_validation",
        source_ref_type: "artifact",
        source_ref_id: `${id}-artifact`,
        summary: "Pass: package checksum matched expected digest.",
        storage_ref: JSON.stringify({ checksum: "abc123", validated: true }),
        created_at: "2026-04-16T08:01:00.000Z",
      },
      {
        id: `${id}-evidence-2`,
        evidence_type: "manual_review",
        source_ref_type: "reviewer_decision",
        source_ref_id: "user-1",
        summary: notes,
        storage_ref: null,
        created_at: "2026-04-16T08:05:00.000Z",
      },
    ],
    status_history: [
      {
        id: `${id}-history-2`,
        status,
        timestamp: "2026-04-16T08:30:00.000Z",
        actor: "trust.officer",
        notes,
      },
      {
        id: `${id}-history-1`,
        status: "pending",
        timestamp: "2026-04-16T08:00:00.000Z",
        actor: "trust-service",
        notes: null,
      },
    ],
    superseded_by_id: null,
  };
}

export async function mockTrustWorkbenchApi(page: Page) {
  const certificationState = new Map<
    string,
    { status: "pending" | "active" | "revoked"; notes: string | null }
  >(
    certificationQueue.map((entry) => [
      entry.id,
      {
        status: entry.status === "revoked" ? "revoked" : "pending",
        notes: entry.revocation_reason ?? null,
      },
    ]),
  );
  const policyBindings = [
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

  await page.route("**/api/v1/trust/certifications?**", async (route) => {
    const url = new URL(route.request().url());
    const search = url.searchParams.get("search") ?? "";
    const status = url.searchParams.get("status") ?? "";
    const sortBy = url.searchParams.get("sort_by") ?? "expiration";
    const pageValue = Number(url.searchParams.get("page") ?? "1");
    const pageSize = Number(url.searchParams.get("page_size") ?? "20");

    const filtered = certificationQueue
      .map((entry) => ({
        ...entry,
        status: certificationState.get(entry.id)?.status ?? "pending",
      }))
      .filter((entry) => {
        const matchesSearch =
          matchSearch(entry.entity_name, search) ||
          matchSearch(entry.entity_fqn, search);
        const matchesStatus = status ? entry.status === status : true;

        return matchesSearch && matchesStatus;
      })
      .sort((left, right) => {
        if (sortBy === "created") {
          return (
            new Date(right.created_at).getTime() - new Date(left.created_at).getTime()
          );
        }
        if (sortBy === "urgency") {
          return right.evidence_count - left.evidence_count;
        }

        return (
          new Date(left.expires_at ?? "9999-12-31").getTime() -
          new Date(right.expires_at ?? "9999-12-31").getTime()
        );
      });

    const items = filtered.slice((pageValue - 1) * pageSize, pageValue * pageSize);

    await route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({
        items,
        total: filtered.length,
        page: pageValue,
        page_size: pageSize,
      }),
      status: 200,
    });
  });

  await page.route("**/api/v1/trust/certifications/*/activate", async (route) => {
    const certificationId = route.request().url().split("/").at(-2)!;
    certificationState.set(certificationId, {
      status: "active",
      notes: "Approved after reviewer validation.",
    });

    await route.fulfill({
      contentType: "application/json",
      body: JSON.stringify(
        buildDetailRecord(certificationId, "active", "Approved after reviewer validation."),
      ),
      status: 200,
    });
  });

  await page.route("**/api/v1/trust/certifications/*/revoke", async (route) => {
    const certificationId = route.request().url().split("/").at(-2)!;
    const body = route.request().postDataJSON() as { reason: string };
    certificationState.set(certificationId, {
      status: "revoked",
      notes: body.reason,
    });

    await route.fulfill({
      contentType: "application/json",
      body: JSON.stringify(buildDetailRecord(certificationId, "revoked", body.reason)),
      status: 200,
    });
  });

  await page.route("**/api/v1/trust/certifications/*/evidence", async (route) => {
    await route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({
        id: "manual-evidence",
        evidence_type: "manual_review",
        source_ref_type: "reviewer_decision",
        source_ref_id: "user-1",
        summary: "Saved reviewer evidence.",
        storage_ref: null,
        created_at: "2026-04-16T08:06:00.000Z",
      }),
      status: 201,
    });
  });

  await page.route("**/api/v1/trust/certifications/*", async (route) => {
    const certificationId = route.request().url().split("/").at(-1)!;
    const state = certificationState.get(certificationId);
    if (!state) {
      await route.fulfill({ status: 404 });
      return;
    }

    await route.fulfill({
      contentType: "application/json",
      body: JSON.stringify(buildDetailRecord(certificationId, state.status, state.notes)),
      status: 200,
    });
  });

  await page.route("**/api/v1/trust/agents/*/trust-profile", async (route) => {
    await route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({
        agent_id: "agent-1",
        agent_fqn: "risk:fraud-monitor",
        tier: "provisional",
        overall_score: 67,
        last_computed_at: "2026-04-16T10:00:00.000Z",
        dimensions: [
          "identity_auth",
          "authorization_access",
          "behavioral_compliance",
          "explainability",
          "evaluation_quality",
          "privacy_data",
          "certification_audit",
        ].map((dimension, index) => ({
          dimension,
          score: dimension === "behavioral_compliance" ? 22 : 70 + index,
          components: [
            {
              name: `${dimension}-component`,
              score: dimension === "behavioral_compliance" ? 22 : 70 + index,
              anomaly_count: dimension === "behavioral_compliance" ? 3 : undefined,
              trend: dimension === "behavioral_compliance" ? "down" : "stable",
            },
          ],
        })),
      }),
      status: 200,
    });
  });

  await page.route("**/api/v1/trust/agents/*/privacy-impact", async (route) => {
    await route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({
        agent_id: "agent-1",
        analysis_timestamp: "2026-04-14T08:00:00.000Z",
        overall_compliant: false,
        data_sources: ["evaluation_results", "behavioral_logs"],
        categories: [
          {
            name: "User PII",
            compliance_status: "violation",
            retention_duration: "45 days",
            concerns: [
              {
                description:
                  "User email addresses exceed the approved retention window.",
                severity: "high",
              },
            ],
            recommendations: ["Reduce retention to 30 days and purge stale records."],
          },
        ],
      }),
      status: 200,
    });
  });

  await page.route("**/api/v1/policies?**", async (route) => {
    await route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({
        items: [
          {
            id: "policy-direct",
            name: "Direct review guardrail",
            description: "Restricts high-risk escalations without manual approval.",
            scope_type: "agent",
            status: "active",
            workspace_id: "workspace-1",
            current_version_id: "policy-direct-v1",
          },
          {
            id: "policy-new",
            name: "Fraud triage policy",
            description: "Applies enhanced triage enforcement for fraud workflows.",
            scope_type: "workspace",
            status: "active",
            workspace_id: "workspace-1",
            current_version_id: "policy-new-v2",
          },
        ],
        total: 2,
        page: 1,
        page_size: 100,
      }),
      status: 200,
    });
  });

  await page.route("**/api/v1/policies/effective/*?**", async (route) => {
    await route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({
        agent_id: "agent-1",
        resolved_rules: policyBindings.map((binding) => ({
          rule: {
            attachment_id: binding.attachmentId,
            policy_name: binding.policyName,
            policy_description: binding.policyDescription,
            target_type: binding.targetType,
            target_id: binding.targetId,
            is_active: binding.isActive,
            created_at: binding.createdAt,
          },
          provenance: {
            rule_id: `${binding.policyId}-rule`,
            policy_id: binding.policyId,
            version_id: binding.policyVersionId,
            scope_level: binding.source === "direct" ? 10 : 1,
            scope_type: binding.scopeType,
            scope_target_id: binding.targetId,
          },
        })),
        conflicts: [],
        source_policies: policyBindings.map((binding) => binding.policyId),
      }),
      status: 200,
    });
  });

  await page.route("**/api/v1/policies/*/attach", async (route) => {
    const policyId = route.request().url().split("/").at(-2)!;
    if (!policyBindings.some((binding) => binding.policyId === policyId)) {
      policyBindings.push({
        attachmentId: "attachment-new",
        policyId,
        policyVersionId: "policy-new-v2",
        policyName: "Fraud triage policy",
        policyDescription: "Applies enhanced triage enforcement for fraud workflows.",
        scopeType: "agent",
        targetType: "agent_revision",
        targetId: "rev-1",
        isActive: true,
        createdAt: "2026-04-16T09:00:00.000Z",
        source: "direct",
        sourceLabel: "direct",
        sourceEntityUrl: null,
        canRemove: true,
      });
    }

    await route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({
        id: "attachment-new",
        policyId,
        policyVersionId: "policy-new-v2",
        targetType: "agent_revision",
        targetId: "rev-1",
        isActive: true,
        createdAt: "2026-04-16T09:00:00.000Z",
      }),
      status: 201,
    });
  });

  await page.route("**/api/v1/policies/*/attach/*", async (route) => {
    const [, policyId, , attachmentId] = route.request().url().split("/").slice(-4);
    const index = policyBindings.findIndex(
      (binding) =>
        binding.policyId === policyId && binding.attachmentId === attachmentId,
    );
    if (index >= 0) {
      policyBindings.splice(index, 1);
    }

    await route.fulfill({ status: 204 });
  });

  await page.route("**/api/v1/fleets?**", async (route) => {
    await route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({
        items: [{ id: "fleet-1", name: "Fraud Detection Fleet" }],
      }),
      status: 200,
    });
  });
}
