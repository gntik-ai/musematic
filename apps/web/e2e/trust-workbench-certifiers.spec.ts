import { expect, test } from "@playwright/test";
import {
  fulfillJson,
  installFrontendState,
  mockCommonAppApi,
  workspaceFixture,
} from "@/e2e/frontend-expansions/helpers";

function buildCertifications() {
  return Array.from({ length: 47 }, (_, index) => ({
    id: `cert-${index + 1}`,
    agent_id: `agent-${index + 1}`,
    agent_fqn: `risk:agent-${String(index + 1).padStart(2, "0")}`,
    agent_revision_id: `rev-${index + 1}`,
    entity_name: `Risk Agent ${index + 1}`,
    entity_fqn: `risk:agent-${String(index + 1).padStart(2, "0")}`,
    entity_type: "agent",
    certification_type: "trust_review",
    status:
      index === 0 ? "active" : index === 1 ? "pending" : index === 2 ? "expired" : "active",
    issued_by: index % 2 === 0 ? "Trust Board" : "External Certifier",
    created_at: `2026-04-${String((index % 20) + 1).padStart(2, "0")}T08:00:00.000Z`,
    updated_at: `2026-04-${String((index % 20) + 1).padStart(2, "0")}T09:00:00.000Z`,
    expires_at: `2026-05-${String((index % 28) + 1).padStart(2, "0")}T00:00:00.000Z`,
    evidence_count: (index % 3) + 1,
  }));
}

test.beforeEach(async ({ page }) => {
  await installFrontendState(page, {
    roles: ["platform_admin", "trust_certifier"],
    workspaceId: workspaceFixture.id,
  });
  await mockCommonAppApi(page);

  let certifiers = [
    {
      id: "certifier-1",
      name: "Trust Board",
      permitted_scopes: ["global"],
      credentials: {
        endpoint: "https://certifier.musematic.dev",
        public_key_fingerprint: "fingerprint-1",
      },
    },
  ];
  const certifications = buildCertifications();

  await page.route("**/api/v1/trust/certifiers", async (route) => {
    if (route.request().method() === "POST") {
      const body = route.request().postDataJSON() as Record<string, unknown>;
      certifiers = [
        ...certifiers,
        {
          id: "certifier-2",
          name: String(body.name ?? "Regulated Certifier"),
          permitted_scopes: Array.isArray(body.permitted_scopes)
            ? body.permitted_scopes.map(String)
            : ["global"],
          credentials: {
            endpoint: String(
              ((body.credentials as Record<string, unknown> | undefined)?.endpoint) ??
                "https://regulated.example.com",
            ),
            public_key_fingerprint: "fingerprint-2",
          },
        },
      ];
      await fulfillJson(route, certifiers.at(-1), 201);
      return;
    }

    await fulfillJson(route, { items: certifiers, total: certifiers.length });
  });

  await page.route("**/api/v1/trust/certifications?**", async (route) => {
    await fulfillJson(route, {
      items: certifications,
      total: certifications.length,
      page: 1,
      page_size: 100,
    });
  });

  await page.route("**/api/v1/registry/agents?**", async (route) => {
    await fulfillJson(route, {
      items: [
        {
          fqn: "risk:fraud-monitor",
          namespace: "risk",
          local_name: "fraud-monitor",
          name: "Fraud Monitor",
          maturity_level: "production",
          status: "active",
          revision_count: 3,
          latest_revision_number: 3,
          updated_at: "2026-04-20T10:00:00.000Z",
          workspace_id: workspaceFixture.id,
        },
        {
          fqn: "risk:kyc-review",
          namespace: "risk",
          local_name: "kyc-review",
          name: "KYC Review",
          maturity_level: "production",
          status: "active",
          revision_count: 2,
          latest_revision_number: 2,
          updated_at: "2026-04-20T10:00:00.000Z",
          workspace_id: workspaceFixture.id,
        },
      ],
      next_cursor: null,
      total: 2,
    });
  });

  await page.route("**/api/v1/trust/agents/*/signals?**", async (route) => {
    const agentId = decodeURIComponent(route.request().url().split("/trust/agents/")[1]?.split("/signals")[0] ?? "");
    const items =
      agentId === "risk:kyc-review"
        ? [
            {
              id: "signal-2",
              agent_id: agentId,
              signal_type: "policy_drift",
              score_contribution: 0.31,
              created_at: "2026-04-20T10:00:00.000Z",
              source_type: "KYC review drift detected",
            },
          ]
        : [
            {
              id: "signal-1",
              agent_id: agentId,
              signal_type: "execution_quality",
              score_contribution: 0.91,
              created_at: "2026-04-20T09:00:00.000Z",
              source_type: "Fraud monitor is stable",
            },
          ];
    await fulfillJson(route, { items, total: items.length });
  });
});

test("manages certifiers, persists expiry sorting, and switches surveillance signals", async ({
  page,
}) => {
  await page.goto("/trust-workbench?tab=certifiers");

  await page.getByLabel("Display name").fill("Bad Certifier");
  await page.getByLabel("Endpoint").fill("http://insecure.example.com");
  await page.getByLabel("PEM public key").fill("not a pem");
  await page.getByRole("button", { name: "Add certifier" }).click();

  await expect(page.getByText("Endpoint must use HTTPS.")).toBeVisible();
  await expect(page.getByText("PEM header/footer is invalid.")).toBeVisible();

  await page.getByLabel("Display name").fill("Regulated Certifier");
  await page.getByLabel("Endpoint").fill("https://regulated.example.com");
  await page
    .getByLabel("PEM public key")
    .fill("-----BEGIN PUBLIC KEY-----\nabc123\n-----END PUBLIC KEY-----");
  await page.getByRole("button", { name: "Add certifier" }).click();

  await expect(page.getByText("Regulated Certifier")).toBeVisible();

  await page.goto("/trust-workbench?tab=expiries");
  await expect(page.getByText("47 total rows")).toBeVisible();
  await page.getByRole("button", { name: "Agent FQN" }).click();
  await expect(page).toHaveURL(/tab=expiries&sort=agent_fqn/);

  await page.goto("/trust-workbench?tab=surveillance");
  await expect(page.getByText("Latest 20 surveillance signals for the selected agent.")).toBeVisible();
  await expect(page.getByText("Fraud monitor is stable")).toBeVisible();
  await page.getByLabel("Agent").selectOption("risk:kyc-review");
  await expect(page.getByText("KYC review drift detected")).toBeVisible();
});
