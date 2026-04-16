import { fireEvent, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { AgentDataTable } from "@/components/features/agent-management/AgentDataTable";
import { renderWithProviders } from "@/test-utils/render";
import { sampleAgent, seedAgentManagementStores } from "@/__tests__/features/agent-management/test-helpers";

const replace = vi.fn();
const fetchNextPage = vi.fn();

vi.mock("next/navigation", () => ({
  usePathname: () => "/agent-management",
  useRouter: () => ({ replace }),
  useSearchParams: () => new URLSearchParams(""),
}));

vi.mock("@/lib/hooks/use-agents", () => ({
  useAgents: () => ({
    agents: [sampleAgent],
    fetchNextPage,
    hasNextPage: false,
    isFetching: false,
    isFetchingNextPage: false,
    isLoading: false,
    total: 1,
  }),
}));

vi.mock("@/lib/hooks/use-namespaces", () => ({
  useNamespaces: () => ({
    data: [
      { namespace: "risk", agent_count: 4 },
      { namespace: "ops", agent_count: 2 },
    ],
  }),
}));

describe("AgentDataTable", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    replace.mockReset();
    fetchNextPage.mockReset();
    seedAgentManagementStores();
  });

  it("renders rows, updates the query string from search and filters, and exposes a detail link", () => {
    renderWithProviders(<AgentDataTable workspace_id="workspace-1" />);

    expect(screen.getByText("KYC Monitor")).toBeInTheDocument();
    expect(screen.getByText("risk:kyc-monitor")).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText("Search agents"), {
      target: { value: "kyc" },
    });
    vi.advanceTimersByTime(300);

    expect(replace).toHaveBeenCalledWith("/agent-management?search=kyc");

    const maturitySelect = screen.getByLabelText("Maturity") as HTMLSelectElement;
    maturitySelect.options[2]!.selected = true;
    fireEvent.change(maturitySelect);

    expect(replace).toHaveBeenCalledWith(
      "/agent-management?maturity=production",
    );

    expect(screen.getByRole("link", { name: /KYC Monitor/i })).toHaveAttribute(
      "href",
      "/agent-management/risk%3Akyc-monitor",
    );
  });
});
