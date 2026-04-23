import { act, fireEvent, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import React from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { DecommissionWizard } from "@/components/features/operator/decommission-wizard";
import { ReliabilityGauges } from "@/components/features/operator/reliability-gauges";
import { VerdictFeed } from "@/components/features/operator/verdict-feed";
import { WarmPoolPanel } from "@/components/features/operator/warm-pool-panel";
import { renderWithProviders } from "@/test-utils/render";
import { seedOperatorStores } from "./test-helpers";

const { wsState, wizardMock, warmPoolProfiles, verdictItems, reliabilityGauges } = vi.hoisted(() => ({
  wsState: {
    warmPoolCallback: null as null | ((event: Record<string, unknown>) => void),
    verdictCallback: null as null | ((event: Record<string, unknown>) => void),
  },
  warmPoolProfiles: [
    {
      name: "small",
      targetReplicas: 5,
      actualReplicas: 4,
      deltaStatus: "within_20_percent",
      lastScalingEvents: [
        { at: "2026-04-20T09:00:00.000Z", from: 3, to: 4, reason: "Scale-up" },
      ],
    },
  ],
  verdictItems: [
    {
      id: "verdict-1",
      offendingAgentFqn: "risk:fraud-monitor",
      verdictType: "policy_violation",
      enforcerAgentFqn: "ops:judge",
      actionTaken: "warn",
      issuedAt: "2026-04-20T09:00:00.000Z",
      rationaleExcerpt: "Policy warning",
    },
  ],
  reliabilityGauges: [
    { id: "api", availabilityPercent: 99.7, windowDays: 30 },
    { id: "execution", availabilityPercent: 99.2, windowDays: 30 },
    { id: "event_delivery", availabilityPercent: 98.7, windowDays: 30 },
  ],
  wizardMock: {
    stage: "warning" as "idle" | "warning" | "dry_run" | "submitting" | "done",
    advance: vi.fn(),
    cancel: vi.fn(),
    confirm: vi.fn().mockResolvedValue(undefined),
    isLoading: false,
    plan: {
      agentFqn: "risk:fraud-monitor",
      dependencies: ["risk:shared-policies", "risk:runtime-dependents"],
      dryRunSummary: ["Status will transition from active to decommissioned."],
    },
  },
}));

vi.mock("recharts", () => ({
  ResponsiveContainer: ({ children }: { children: React.ReactNode }) => (
    <div data-testid="responsive-container">{children}</div>
  ),
  RadialBarChart: ({ children }: { children: React.ReactNode }) => <svg>{children}</svg>,
  RadialBar: () => <path data-testid="radial-bar" />,
  PolarAngleAxis: () => <g data-testid="polar-angle-axis" />,
}));

vi.mock("@/components/ui/sheet", () => ({
  Sheet: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  SheetContent: ({ children }: { children: React.ReactNode }) => <section>{children}</section>,
  SheetDescription: ({ children }: { children: React.ReactNode }) => <p>{children}</p>,
  SheetTitle: ({ children }: { children: React.ReactNode }) => <h2>{children}</h2>,
}));

vi.mock("@/lib/ws", () => ({
  wsClient: {
    connect: vi.fn(),
    subscribe: (channel: string, callback: (event: Record<string, unknown>) => void) => {
      if (channel === "warm-pool") {
        wsState.warmPoolCallback = callback;
      }
      if (channel === "governance-verdicts") {
        wsState.verdictCallback = callback;
      }
      return vi.fn();
    },
  },
}));

vi.mock("@/lib/hooks/use-warm-pool-status", () => ({
  useWarmPoolStatus: () => ({ profiles: warmPoolProfiles }),
}));

vi.mock("@/lib/hooks/use-verdict-feed", () => ({
  useVerdictFeed: () => ({ items: verdictItems }),
}));

vi.mock("@/lib/hooks/use-reliability-gauges", () => ({
  useReliabilityGauges: () => ({ gauges: reliabilityGauges }),
}));

vi.mock("@/lib/hooks/use-decommission-wizard", () => ({
  useDecommissionWizard: () => ({
    stage: wizardMock.stage,
    plan: wizardMock.plan,
    advance: wizardMock.advance,
    cancel: wizardMock.cancel,
    confirm: wizardMock.confirm,
    confirmFqn: "",
    setConfirmFqn: vi.fn(),
    isLoading: wizardMock.isLoading,
  }),
}));

describe("operator expansions", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    seedOperatorStores();
    wsState.warmPoolCallback = null;
    wsState.verdictCallback = null;
    wizardMock.stage = "warning";
    wizardMock.isLoading = false;
  });

  it("updates the warm-pool card from websocket events and opens the scaling drawer", async () => {
    renderWithProviders(<WarmPoolPanel />);

    expect(screen.getByText("small")).toBeInTheDocument();
    expect(screen.getByText("4 actual / 5 target")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /small/i }));
    expect(screen.getByText("Recent scaling activity")).toBeInTheDocument();

    act(() => {
      wsState.warmPoolCallback?.({
        type: "warm-pool.updated",
        payload: {
          profile: {
            name: "small",
            targetReplicas: 5,
            actualReplicas: 2,
            deltaStatus: "below_target",
          },
        },
      });
    });

    await waitFor(() => expect(screen.getByText("2 actual / 5 target")).toBeInTheDocument());
    expect(screen.getByText("Below target")).toBeInTheDocument();
  });

  it("prepends issued verdicts and strikes superseded ones", async () => {
    renderWithProviders(<VerdictFeed workspaceId="workspace-1" />);

    act(() => {
      wsState.verdictCallback?.({
        type: "verdict.issued",
        payload: {
          id: "verdict-2",
          workspace_id: "workspace-1",
          target_agent_fqn: "risk:kyc-review",
          verdict_type: "safety_violation",
          judge_agent_fqn: "ops:judge",
          recommended_action: "block",
        },
      });
    });

    await waitFor(() => expect(screen.getByText("risk:kyc-review")).toBeInTheDocument());

    act(() => {
      wsState.verdictCallback?.({
        type: "verdict.superseded",
        payload: { id: "verdict-1", workspace_id: "workspace-1" },
      });
    });

    await waitFor(() => {
      const originalEntry = screen.getByText("risk:fraud-monitor").closest("article");
      expect(originalEntry).toHaveClass("line-through");
    });
  });

  it("opens the typed confirmation path from the decommission wizard", async () => {
    const user = userEvent.setup();
    wizardMock.stage = "dry_run";
    renderWithProviders(
      <DecommissionWizard agentFqn="risk:fraud-monitor" isOpen onClose={vi.fn()} />,
    );

    await user.click(screen.getByRole("button", { name: "Next" }));
    await user.type(screen.getByPlaceholderText("risk:fraud-monitor"), "risk:fraud-monitor");
    await user.click(screen.getByRole("button", { name: "Decommission" }));

    await waitFor(() => expect(wizardMock.confirm).toHaveBeenCalledTimes(1));
  });

  it("renders warning copy before confirmation and closes the completed state", async () => {
    const onClose = vi.fn();
    const user = userEvent.setup();

    wizardMock.stage = "warning";
    renderWithProviders(
      <DecommissionWizard agentFqn="risk:fraud-monitor" isOpen onClose={onClose} />,
    );

    expect(screen.getByText(/downstream dependencies/i)).toBeInTheDocument();
    expect(screen.getByText("risk:shared-policies")).toBeInTheDocument();

    wizardMock.stage = "done";
    renderWithProviders(
      <DecommissionWizard agentFqn="risk:fraud-monitor" isOpen onClose={onClose} />,
    );

    expect(screen.getByText("Agent marked for decommission.")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Close" }));
    expect(onClose).toHaveBeenCalled();
  });

  it("renders the three reliability gauges", () => {
    renderWithProviders(<ReliabilityGauges windowDays={30} />);

    expect(screen.getByText("API")).toBeInTheDocument();
    expect(screen.getByText("Execution")).toBeInTheDocument();
    expect(screen.getByText("Event delivery")).toBeInTheDocument();
    expect(screen.getByText("99.70%")).toBeInTheDocument();
  });
});
