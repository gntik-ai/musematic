import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { AgentProfileA2aTab } from "@/components/features/agents/agent-profile-a2a-tab";
import { AgentProfileContractsTab } from "@/components/features/agents/agent-profile-contracts-tab";
import { AgentProfileMcpTab } from "@/components/features/agents/agent-profile-mcp-tab";
import { renderWithProviders } from "@/test-utils/render";
import { seedAgentManagementStores } from "./test-helpers";

const disconnectServerSpy = vi.fn().mockResolvedValue(undefined);
let a2aCard: { card: Record<string, unknown> | null; isLoading: boolean } = {
  card: { agent: "risk:kyc-monitor", skills: ["audit"] },
  isLoading: false,
};

vi.mock("@/lib/hooks/use-agent-contracts", () => ({
  useAgentContracts: () => ({
    contracts: [
      {
        id: "contract-1",
        version: "1",
        status: "superseded",
        publishedAt: "2026-04-10T00:00:00.000Z",
        supersededAt: "2026-04-11T00:00:00.000Z",
        signatories: ["risk:kyc-monitor"],
        documentExcerpt: "Version one excerpt",
      },
      {
        id: "contract-2",
        version: "2",
        status: "superseded",
        publishedAt: "2026-04-12T00:00:00.000Z",
        supersededAt: "2026-04-13T00:00:00.000Z",
        signatories: ["risk:kyc-monitor"],
        documentExcerpt: "Version two excerpt",
      },
      {
        id: "contract-3",
        version: "3",
        status: "active",
        publishedAt: "2026-04-14T00:00:00.000Z",
        supersededAt: null,
        signatories: ["risk:kyc-monitor"],
        documentExcerpt: "Version three excerpt",
      },
    ],
    isLoading: false,
  }),
}));

vi.mock("@/lib/hooks/use-a2a-agent-card", () => ({
  useA2aAgentCard: () => a2aCard,
}));

vi.mock("@/lib/hooks/use-mcp-servers", () => ({
  useMcpServers: () => ({
    servers: [
      {
        id: "server-1",
        name: "Compliance MCP",
        endpoint: "https://mcp.musematic.dev",
        capabilityCounts: { tools: 4, resources: 2 },
        healthStatus: "healthy",
        lastHealthCheckAt: "2026-04-20T10:00:00.000Z",
      },
    ],
    isLoading: false,
  }),
  useMcpServerMutations: () => ({
    disconnectServer: { mutateAsync: disconnectServerSpy, isPending: false },
  }),
}));

describe("agent profile expansions", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    seedAgentManagementStores();
    a2aCard = {
      card: { agent: "risk:kyc-monitor", skills: ["audit"] },
      isLoading: false,
    };
  });

  it("enables the diff dialog once two contracts are selected", async () => {
    const user = userEvent.setup();
    renderWithProviders(<AgentProfileContractsTab agentId="risk:kyc-monitor" />);

    const checkboxes = screen.getAllByRole("checkbox");
    expect(screen.getByRole("button", { name: "Diff" })).toBeDisabled();

    await user.click(checkboxes[0]!);
    await user.click(checkboxes[1]!);
    await user.click(screen.getByRole("button", { name: "Diff" }));

    expect(screen.getByRole("dialog")).toBeInTheDocument();
    expect(screen.getAllByText("Version one excerpt")).toHaveLength(2);
    expect(screen.getAllByText("Version two excerpt")).toHaveLength(2);
  });

  it("renders the published A2A JSON via the code block", () => {
    renderWithProviders(<AgentProfileA2aTab agentId="risk:kyc-monitor" />);

    expect(screen.getByText("A2A profile")).toBeInTheDocument();
    expect(screen.getByText(/risk:kyc-monitor/)).toBeInTheDocument();
  });

  it("shows the configure CTA when no A2A card is published", () => {
    a2aCard = { card: null, isLoading: false };
    renderWithProviders(<AgentProfileA2aTab agentId="risk:kyc-monitor" />);

    expect(
      screen.getByText("No A2A card is published for this agent yet."),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Configure" })).toBeInTheDocument();
  });

  it("confirms MCP disconnection before invoking the mutation", async () => {
    const user = userEvent.setup();
    renderWithProviders(<AgentProfileMcpTab agentId="risk:kyc-monitor" />);

    await user.click(screen.getByRole("button", { name: "Disconnect" }));
    expect(screen.getByText("Disconnect MCP server")).toBeInTheDocument();

    const disconnectButtons = screen.getAllByRole("button", { name: "Disconnect" });
    await user.click(disconnectButtons[1]!);

    await waitFor(() =>
      expect(disconnectServerSpy).toHaveBeenCalledWith({ serverId: "server-1" }),
    );
  });
});
