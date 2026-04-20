import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { DecisionRationalePanel } from "@/components/features/conversations/decision-rationale-panel";

describe("DecisionRationalePanel", () => {
  it("renders an empty state when rationale is unavailable", () => {
    render(<DecisionRationalePanel rationale={null} />);

    expect(
      screen.getByText(/no decision rationale recorded/i),
    ).toBeInTheDocument();
  });

  it("renders collapsible rationale sections", async () => {
    const user = userEvent.setup();

    render(
      <DecisionRationalePanel
        rationale={{
          toolChoices: [
            {
              tool: "tool_selection",
              reason: "Used the most relevant finance helper.",
            },
          ],
          retrievedMemories: [
            {
              memoryId: "memory-1",
              relevanceScore: 0.88,
              excerpt: "APAC revenue acceleration remained strongest in Q2.",
            },
          ],
          riskFlags: [
            {
              category: "policy_guard",
              severity: "medium",
              note: "Compliance claims required a second source.",
            },
          ],
          policyChecks: [
            {
              policyId: "policy-1",
              policyName: "policy_guard",
              verdict: "warn",
            },
          ],
        }}
      />,
    );

    expect(screen.getByText(/tool_selection/i)).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /toggle retrieved memories/i }));

    expect(
      screen.getByText(/apac revenue acceleration remained strongest in q2/i),
    ).toBeInTheDocument();
  });
});
