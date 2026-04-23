import { fireEvent, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { DebateTranscript } from "@/components/features/execution/debate-transcript";
import { renderWithProviders } from "@/test-utils/render";

vi.mock("@/lib/hooks/use-debate-transcript", () => ({
  useDebateTranscript: () => ({
    data: [
      {
        participantAgentFqn: "agents.alpha",
        participantDisplayName: "alpha",
        participantIsDeleted: false,
        position: "support",
        content: "Prefer accuracy.",
        reasoningTraceId: "trace-step-145",
        timestamp: "2026-04-13T09:36:00.000Z",
      },
      {
        participantAgentFqn: "deleted:agent",
        participantDisplayName: "Removed agent",
        participantIsDeleted: true,
        position: "oppose",
        content: "Challenge freshness assumptions.",
        reasoningTraceId: "trace-step-146",
        timestamp: "2026-04-13T09:36:09.000Z",
      },
    ],
    isLoading: false,
  }),
}));

describe("DebateTranscript", () => {
  it("renders tombstones for deleted participants and exposes the reasoning trace collapsible", () => {
    renderWithProviders(<DebateTranscript executionId="execution-1" />);

    expect(screen.getByText("Agent no longer exists")).toBeInTheDocument();
    const [firstReasoningTraceToggle] = screen.getAllByRole("button", { name: /reasoning trace/i });
    expect(firstReasoningTraceToggle).toBeDefined();
    fireEvent.click(firstReasoningTraceToggle!);
    expect(screen.getByText(/reference: trace-step-145/i)).toBeInTheDocument();
  });
});
