import { fireEvent, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ReasoningTracePanel } from "@/components/features/operator/ReasoningTracePanel";
import { renderWithProviders } from "@/test-utils/render";
import { sampleReasoningTrace } from "@/__tests__/features/operator/test-helpers";

describe("ReasoningTracePanel", () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  it("renders all steps and exposes the self-correction chain when a step is expanded", () => {
    renderWithProviders(
      <ReasoningTracePanel
        isLoading={false}
        trace={sampleReasoningTrace}
      />,
    );

    expect(screen.getByText("3820 tokens · 1820ms · 2 corrections")).toBeInTheDocument();
    expect(screen.getByText("Step 1")).toBeInTheDocument();
    expect(screen.getByText("Step 2")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /Step 1/i }));
    expect(screen.getByText("Self-correction chain")).toBeInTheDocument();
    expect(
      screen.getByText("Original output over-weighted a stale device fingerprint."),
    ).toBeInTheDocument();
    expect(
      screen.getByText("Show full output"),
    ).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Show full output" }));
    expect(
      screen.getByText(
        "Full output trace for step 1: confidence 0.92 with a two-hop entity match.",
      ),
    ).toBeInTheDocument();
  });
});
