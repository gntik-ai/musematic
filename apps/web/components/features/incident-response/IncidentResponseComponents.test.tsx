import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import {
  IncidentTable,
  IntegrationConfigForm,
  RunbookEditor,
  RunbookViewer,
  TimelineSourceCoverageBanner,
  integrationConfigSchema,
  runbookEditorSchema,
} from ".";
import type { IncidentResponse, RunbookResponse } from "@/lib/api/incidents";

const runbook: RunbookResponse = {
  id: "runbook-1",
  scenario: "kafka_lag",
  title: "Kafka lag",
  symptoms: "Consumers are behind.",
  diagnostic_commands: [{ command: "kafka-consumer-groups.sh --describe", description: "Check lag." }],
  remediation_steps: "Scale consumers.",
  escalation_path: "Streaming on-call.",
  status: "active",
  version: 1,
  created_at: "2026-04-26T00:00:00Z",
  updated_at: "2026-04-26T00:00:00Z",
  updated_by: null,
  is_stale: true,
};

describe("incident response components", () => {
  it("renders stale runbook state and copies diagnostic commands", async () => {
    const writeText = vi.fn();
    Object.defineProperty(navigator, "clipboard", {
      configurable: true,
      value: { writeText },
    });

    render(<RunbookViewer runbook={runbook} />);
    await userEvent.click(screen.getByRole("button", { name: /kafka-consumer-groups/i }));

    expect(screen.getByText("Stale")).toBeInTheDocument();
    expect(writeText).toHaveBeenCalledWith("kafka-consumer-groups.sh --describe");
  });

  it("renders authoring CTA when an incident has no runbook", () => {
    render(<RunbookViewer authoringLink="/operator/runbooks/new?scenario=x" runbook={null} />);

    expect(screen.getByText("No runbook for this scenario.")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Author runbook/i })).toHaveAttribute(
      "href",
      "/operator/runbooks/new?scenario=x",
    );
  });

  it("validates runbook editor input and stale version presentation", () => {
    const valid = runbookEditorSchema.safeParse({
      expected_version: 1,
      title: "Kafka lag",
      symptoms: "Consumers are behind.",
      diagnostic_commands: [{ command: "kafka", description: "Check lag." }],
      remediation_steps: "Scale consumers.",
      escalation_path: "Streaming on-call.",
      status: "active",
    });
    const invalid = runbookEditorSchema.safeParse({
      expected_version: 1,
      title: "",
      symptoms: "",
      diagnostic_commands: [],
      remediation_steps: "",
      escalation_path: "",
      status: "active",
    });

    render(<RunbookEditor runbook={runbook} staleVersion={2} onSubmit={vi.fn()} />);

    expect(valid.success).toBe(true);
    expect(invalid.success).toBe(false);
    expect(screen.getByText("Stale settings detected")).toBeInTheDocument();
  });

  it("shows timeline coverage only when a source is incomplete", () => {
    const complete = {
      audit_chain: "complete",
      execution_journal: "complete",
      kafka: "complete",
      reasons: {},
    } as const;
    const { rerender } = render(<TimelineSourceCoverageBanner coverage={complete} />);
    expect(screen.queryByText(/coverage is incomplete/i)).not.toBeInTheDocument();

    rerender(
      <TimelineSourceCoverageBanner
        coverage={{ ...complete, kafka: "unavailable", reasons: { kafka: "offline" } }}
      />,
    );
    expect(screen.getByText(/coverage is incomplete/i)).toBeInTheDocument();
    expect(screen.getByText(/kafka: unavailable/i)).toBeInTheDocument();
  });

  it("validates integration vault reference and provider selection", () => {
    const valid = integrationConfigSchema.safeParse({
      provider: "pagerduty",
      integration_key_ref: "incident-response/integrations/pagerduty-primary",
      enabled: true,
      critical: "P1",
      high: "P2",
      warning: "P3",
      info: "P5",
    });
    const invalid = integrationConfigSchema.safeParse({
      provider: "pagerduty",
      integration_key_ref: "secret/plaintext",
      enabled: true,
      critical: "P1",
      high: "P2",
      warning: "P3",
      info: "P5",
    });

    render(<IntegrationConfigForm onSubmit={vi.fn()} />);

    expect(valid.success).toBe(true);
    expect(invalid.success).toBe(false);
    expect(screen.getByLabelText("Provider")).toBeInTheDocument();
    expect(screen.getByLabelText("Vault path")).toHaveValue("incident-response/integrations/");
  });

  it("renders incident table happy path", () => {
    const incident: IncidentResponse = {
      id: "incident-1",
      condition_fingerprint: "fingerprint",
      severity: "critical",
      status: "open",
      title: "Kafka lag above threshold",
      description: "Lag storm",
      triggered_at: "2026-04-26T00:00:00Z",
      resolved_at: null,
      related_executions: [],
      related_event_ids: [],
      runbook_scenario: "kafka_lag",
      alert_rule_class: "kafka_lag",
      post_mortem_id: null,
    };

    render(
      <IncidentTable
        incidents={[incident]}
        severityFilter=""
        statusFilter="open"
        onRowClick={vi.fn()}
        onSeverityFilterChange={vi.fn()}
        onStatusFilterChange={vi.fn()}
      />,
    );

    expect(screen.getByText("Kafka lag above threshold")).toBeInTheDocument();
    expect(screen.getByText("critical")).toBeInTheDocument();
  });
});
