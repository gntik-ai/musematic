import { expect, test, type Page } from "@playwright/test";
import { installOperatorState } from "@/e2e/operator/helpers";

test.beforeEach(async ({ page }) => {
  await installOperatorState(page);
  await mockIncidentResponseApi(page);
});

test("operator can resolve an incident and complete the post-mortem flow", async ({ page }) => {
  await page.request.post("/api/v1/_e2e/incidents/seed/kafka-lag");
  await page.goto("/operator/incidents");

  await expect(page.getByRole("heading", { name: "Incidents" })).toBeVisible();
  await expect(page.getByText("Kafka lag above threshold")).toBeVisible();

  await page.getByText("Kafka lag above threshold").click();
  await expect(page.getByText("Consumer group lag is above threshold.")).toBeVisible();
  await expect(page.getByText("Kafka lag runbook")).toBeVisible();
  await expect(page.getByText("kafka-consumer-groups.sh --describe")).toBeVisible();

  await page.getByRole("button", { name: /Resolve/i }).click();
  await expect(page.getByRole("button", { name: /Start post-mortem/i })).toBeEnabled();
  await page.getByRole("button", { name: /Start post-mortem/i }).click();

  await expect(page).toHaveURL(/\/operator\/incidents\/incident-1\/post-mortem$/);
  await expect(page.getByRole("heading", { name: "Timeline" })).toBeVisible();
  await page.getByLabel("Impact assessment").fill("Kafka consumers delayed workflow events.");
  await page.getByLabel("Root cause").fill("A consumer deployment was under-replicated.");
  await page.getByLabel("Action items").fill('[{"owner":"streaming","task":"raise replicas"}]');
  await page.getByRole("button", { name: /Save sections/i }).click();
  await page.getByRole("button", { name: /Mark blameless/i }).click();
  await page.getByLabel("Distribution recipients").fill("ops@example.com, bad@example.com");
  await page.getByRole("button", { name: /Distribute/i }).click();

  await expect(page.getByText("ops@example.com: delivered")).toBeVisible();
  await expect(page.getByText("bad@example.com: failed:inactive recipient")).toBeVisible();
});

async function mockIncidentResponseApi(page: Page) {
  const runbook = {
    id: "runbook-1",
    scenario: "kafka_lag",
    title: "Kafka lag runbook",
    symptoms: "Consumer lag is increasing.",
    diagnostic_commands: [
      { command: "kafka-consumer-groups.sh --describe", description: "Inspect group lag." },
    ],
    remediation_steps: "Scale consumers and confirm offsets advance.",
    escalation_path: "Streaming platform on-call.",
    status: "active",
    version: 1,
    created_at: "2026-04-26T00:00:00Z",
    updated_at: "2026-04-26T00:00:00Z",
    updated_by: null,
    is_stale: false,
  };
  const incident = {
    id: "incident-1",
    condition_fingerprint: "kafka_lag:workspace",
    severity: "critical",
    status: "open",
    title: "Kafka lag above threshold",
    description: "Consumer group lag is above threshold.",
    triggered_at: "2026-04-26T10:00:00Z",
    resolved_at: null as string | null,
    related_executions: ["exec-run-0001"],
    related_event_ids: ["event-1"],
    runbook_scenario: "kafka_lag",
    alert_rule_class: "kafka_lag",
    post_mortem_id: null as string | null,
  };
  let postMortem = {
    id: "postmortem-1",
    incident_id: incident.id,
    status: "draft",
    timeline: [
      {
        id: "timeline-1",
        timestamp: "2026-04-26T10:01:00Z",
        source: "audit_chain",
        event_type: "audit.changed",
        summary: "Alert rule changed state.",
        topic: null,
        payload_summary: {},
      },
      {
        id: "timeline-2",
        timestamp: "2026-04-26T10:02:00Z",
        source: "execution_journal",
        event_type: "execution.failed",
        summary: "Execution delayed by Kafka lag.",
        topic: null,
        payload_summary: {},
      },
    ],
    timeline_blob_ref: null,
    timeline_source_coverage: {
      audit_chain: "complete",
      execution_journal: "complete",
      kafka: "complete",
      reasons: {},
    },
    impact_assessment: null as string | null,
    root_cause: null as string | null,
    action_items: null as Array<Record<string, unknown>> | null,
    distribution_list: null as Array<{ recipient: string; outcome: string }> | null,
    linked_certification_ids: [],
    blameless: true,
    created_at: "2026-04-26T10:10:00Z",
    created_by: "user-1",
    published_at: null,
    distributed_at: null as string | null,
  };

  await page.route("**/api/v1/**", async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const path = url.pathname;

    if (path.startsWith("/api/v1/_e2e/incidents/seed/")) {
      await route.fulfill({ contentType: "application/json", body: JSON.stringify(incident) });
      return;
    }

    if (path === "/api/v1/incidents" && request.method() === "GET") {
      await route.fulfill({ contentType: "application/json", body: JSON.stringify([incident]) });
      return;
    }

    if (path === "/api/v1/incidents/incident-1" && request.method() === "GET") {
      await route.fulfill({
        contentType: "application/json",
        body: JSON.stringify({
          ...incident,
          external_alerts: [],
          runbook,
          runbook_authoring_link: null,
          runbook_scenario_unmapped: false,
        }),
      });
      return;
    }

    if (path === "/api/v1/incidents/incident-1/resolve" && request.method() === "POST") {
      incident.status = "resolved";
      incident.resolved_at = "2026-04-26T10:05:00Z";
      await route.fulfill({ contentType: "application/json", body: JSON.stringify(incident) });
      return;
    }

    if (path === "/api/v1/incidents/incident-1/post-mortem" && request.method() === "POST") {
      incident.post_mortem_id = postMortem.id;
      await route.fulfill({ contentType: "application/json", body: JSON.stringify(postMortem) });
      return;
    }

    if (path === "/api/v1/incidents/incident-1/post-mortem" && request.method() === "GET") {
      await route.fulfill({ contentType: "application/json", body: JSON.stringify(postMortem) });
      return;
    }

    if (path === "/api/v1/post-mortems/postmortem-1" && request.method() === "PATCH") {
      const payload = JSON.parse(request.postData() ?? "{}");
      postMortem = { ...postMortem, ...payload };
      await route.fulfill({ contentType: "application/json", body: JSON.stringify(postMortem) });
      return;
    }

    if (path === "/api/v1/post-mortems/postmortem-1/blameless") {
      postMortem.blameless = true;
      await route.fulfill({ contentType: "application/json", body: JSON.stringify(postMortem) });
      return;
    }

    if (path === "/api/v1/post-mortems/postmortem-1/distribute") {
      postMortem = {
        ...postMortem,
        status: "distributed",
        distribution_list: [
          { recipient: "ops@example.com", outcome: "delivered" },
          { recipient: "bad@example.com", outcome: "failed:inactive recipient" },
        ],
      };
      await route.fulfill({ contentType: "application/json", body: JSON.stringify(postMortem) });
      return;
    }

    await route.fulfill({ status: 404, contentType: "application/json", body: "{}" });
  });
}
