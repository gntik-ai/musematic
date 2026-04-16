import { fireEvent, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { PrivacyImpactPanel } from "@/components/features/trust-workbench/PrivacyImpactPanel";
import { renderWithProviders } from "@/test-utils/render";
import {
  sampleCompliantPrivacyAnalysis,
  samplePrivacyAnalysis,
  seedTrustWorkbenchStores,
} from "@/__tests__/features/trust-workbench/test-helpers";

const toast = vi.fn();
const privacyHook = vi.fn();

vi.mock("@/lib/hooks/use-toast", () => ({
  useToast: () => ({ toast }),
}));

vi.mock("@/lib/hooks/use-privacy-impact", () => ({
  usePrivacyImpact: (agentId: string) => privacyHook(agentId),
}));

describe("PrivacyImpactPanel", () => {
  beforeEach(() => {
    toast.mockReset();
    privacyHook.mockReset();
    seedTrustWorkbenchStores();
  });

  it("renders compliant analysis metadata and the summary banner", () => {
    privacyHook.mockReturnValue({
      data: sampleCompliantPrivacyAnalysis,
      isError: false,
      isLoading: false,
    });

    renderWithProviders(<PrivacyImpactPanel agentId="agent-1" />);

    expect(screen.getByText("No privacy concerns identified.")).toBeInTheDocument();
    expect(screen.getByText(/Sources: evaluation_results, behavioral_logs/i)).toBeInTheDocument();
  });

  it("renders violations and stale analysis actions", () => {
    privacyHook.mockReturnValue({
      data: {
        ...samplePrivacyAnalysis,
        analysisTimestamp: "2026-04-14T08:00:00.000Z",
      },
      isError: false,
      isLoading: false,
    });

    renderWithProviders(<PrivacyImpactPanel agentId="agent-1" />);

    expect(screen.getByText("User email addresses exceed the approved retention window.")).toBeInTheDocument();
    expect(screen.getByText(/Reduce retention to 30 days/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Request Re-analysis" })).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Request Re-analysis" }));
    expect(toast).toHaveBeenCalledWith(
      expect.objectContaining({
        title: "Request re-analysis",
      }),
    );
  });
});
