import { fireEvent, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { ReactCycleViewer } from "@/components/features/execution/react-cycle-viewer";
import { renderWithProviders } from "@/test-utils/render";

vi.mock("@/lib/hooks/use-react-cycles", () => ({
  useReactCycles: () => ({
    data: [
      {
        index: 1,
        thought: "Check prior evidence.",
        action: {
          tool: "knowledge.search",
          args: { query: "customer-123" },
        },
        observation: "Evidence retrieved successfully.",
        durationMs: 540,
      },
    ],
    isLoading: false,
  }),
}));

describe("ReactCycleViewer", () => {
  it("renders collapsible Thought, Action, and Observation sections", () => {
    renderWithProviders(<ReactCycleViewer executionId="execution-1" />);

    fireEvent.click(screen.getByRole("button", { name: "Thought" }));
    expect(screen.getByText("Check prior evidence.")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Action" }));
    expect(screen.getAllByText(/knowledge.search/)).toHaveLength(2);

    fireEvent.click(screen.getByRole("button", { name: "Observation" }));
    expect(screen.getByText("Evidence retrieved successfully.")).toBeInTheDocument();
  });
});
