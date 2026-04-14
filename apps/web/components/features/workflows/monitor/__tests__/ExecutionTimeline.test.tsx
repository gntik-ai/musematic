import { fireEvent, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it } from "vitest";
import { ExecutionTimeline } from "@/components/features/workflows/monitor/ExecutionTimeline";
import { renderWithProviders } from "@/test-utils/render";
import { executionFixtures } from "@/mocks/handlers/executions";

describe("ExecutionTimeline", () => {
  beforeEach(() => {
    executionFixtures.journalByExecutionId["execution-empty"] = [];
    executionFixtures.journalByExecutionId["execution-paged"] = Array.from(
      { length: 24 },
      (_, index) => ({
        id: `execution-paged-evt-${index + 1}`,
        execution_id: "execution-paged",
        sequence: index + 1,
        event_type: "STEP_COMPLETED" as const,
        step_id: `step_${index + 1}`,
        agent_fqn: "operations/context-loader",
        payload: {},
        created_at: new Date(`2026-04-13T09:${String(index).padStart(2, "0")}:00.000Z`).toISOString(),
      }),
    );
  });

  it("renders execution journal events inside an aria-live region", async () => {
    renderWithProviders(<ExecutionTimeline executionId="execution-1" />);

    expect(await screen.findByText("REASONING_TRACE_EMITTED")).toBeInTheDocument();
    expect(screen.getByText("STEP_COMPLETED")).toBeInTheDocument();
    expect(screen.getByText("REASONING_TRACE_EMITTED").closest("[aria-live='polite']")).toBeInTheDocument();
  });

  it("loads additional event pages on demand", async () => {
    renderWithProviders(<ExecutionTimeline executionId="execution-paged" />);

    await screen.findAllByText("STEP_COMPLETED");
    expect(screen.getAllByText("STEP_COMPLETED")).toHaveLength(20);

    fireEvent.click(screen.getByRole("button", { name: /Load more events/i }));

    await waitFor(() => {
      expect(screen.getAllByText("STEP_COMPLETED")).toHaveLength(24);
    });
  });

  it("shows the empty state when the journal has no events", async () => {
    renderWithProviders(<ExecutionTimeline executionId="execution-empty" />);

    expect(await screen.findByText("Timeline is empty")).toBeInTheDocument();
  });
});
