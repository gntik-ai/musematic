import { fireEvent, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { CertificationDetailView } from "@/components/features/trust-workbench/CertificationDetailView";
import { renderWithProviders } from "@/test-utils/render";
import {
  sampleCertificationDetail,
  sampleTrustRadarProfile,
  seedTrustWorkbenchStores,
} from "@/__tests__/features/trust-workbench/test-helpers";

const navigationMocks = vi.hoisted(() => ({
  refresh: vi.fn(),
  replace: vi.fn(),
}));

let currentSearch = "";

vi.mock("next/navigation", () => ({
  usePathname: () => "/trust-workbench/cert-1",
  useRouter: () => navigationMocks,
  useSearchParams: () => new URLSearchParams(currentSearch),
}));

vi.mock("@/lib/hooks/use-trust-radar", () => ({
  useTrustRadar: (agentId: string | null) => ({
    data: agentId ? sampleTrustRadarProfile : null,
    isError: false,
    isLoading: false,
  }),
}));

describe("CertificationDetailView", () => {
  beforeEach(() => {
    currentSearch = "";
    navigationMocks.refresh.mockReset();
    navigationMocks.replace.mockReset();
    seedTrustWorkbenchStores();
  });

  it("renders entity details, timeline events, evidence items, and the reviewer form by default", () => {
    renderWithProviders(
      <CertificationDetailView
        certification={sampleCertificationDetail}
        workspaceId="workspace-1"
      />,
    );

    expect(
      screen.getByRole("heading", { name: "Fraud Monitor" }),
    ).toBeInTheDocument();
    expect(screen.getByText(/Awaiting manual decision/i)).toBeInTheDocument();
    expect(screen.getByText("Reviewer decision")).toBeInTheDocument();
    expect(screen.getByText("Package validation")).toBeInTheDocument();

    fireEvent.click(
      screen.getByRole("button", { name: /Package validation/i }),
    );

    expect(screen.getByText("Supporting data")).toBeInTheDocument();
  });

  it("routes tab changes through the query string", () => {
    renderWithProviders(
      <CertificationDetailView
        certification={sampleCertificationDetail}
        workspaceId="workspace-1"
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: "Trust radar" }));
    expect(navigationMocks.replace).toHaveBeenCalledWith(
      "/trust-workbench/cert-1?tab=trust-radar",
    );
  });
});
