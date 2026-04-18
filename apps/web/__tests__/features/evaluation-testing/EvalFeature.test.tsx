import { fireEvent, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { EvalSuiteDataTable } from "@/components/features/eval/EvalSuiteDataTable";
import { CreateEvalSuiteForm } from "@/components/features/eval/CreateEvalSuiteForm";
import { renderWithProviders } from "@/test-utils/render";
import type { EvaluationRunResponse } from "@/types/evaluation";

const mutationMocks = vi.hoisted(() => ({
  addCase: vi.fn(),
  createEvalSet: vi.fn(),
}));

vi.mock("@/lib/hooks/use-eval-mutations", () => ({
  useEvalMutations: () => ({
    createEvalSet: {
      mutateAsync: mutationMocks.createEvalSet,
      isPending: false,
      error: null,
    },
    addCase: {
      mutateAsync: mutationMocks.addCase,
      isPending: false,
      error: null,
    },
    runEval: {
      mutateAsync: vi.fn(),
      isPending: false,
      error: null,
    },
    createExperiment: {
      mutateAsync: vi.fn(),
      isPending: false,
      error: null,
    },
    runAte: {
      mutateAsync: vi.fn(),
      isPending: false,
      error: null,
    },
  }),
}));

const evalSuites: Array<
  {
    last_run?: Partial<EvaluationRunResponse> | null;
  } & {
    id: string;
    workspace_id: string;
    name: string;
    description: string | null;
    scorer_config: Record<string, unknown>;
    pass_threshold: number;
    status: "active" | "archived";
    created_by: string;
    created_at: string;
    updated_at: string;
  }
> = [
  {
    id: "eval-suite-1",
    workspace_id: "workspace-1",
    name: "KYC Agent Quality",
    description: "Checks onboarding answers",
    scorer_config: {},
    pass_threshold: 0.7,
    status: "active",
    created_by: "user-1",
    created_at: "2026-04-18T08:00:00.000Z",
    updated_at: "2026-04-18T08:00:00.000Z",
    last_run: {
      agent_fqn: "risk:kyc-agent",
      aggregate_score: 0.92,
      completed_at: "2026-04-18T08:30:00.000Z",
    },
  },
  {
    id: "eval-suite-2",
    workspace_id: "workspace-1",
    name: "Escalation Safety",
    description: null,
    scorer_config: {},
    pass_threshold: 0.8,
    status: "archived",
    created_by: "user-1",
    created_at: "2026-04-17T08:00:00.000Z",
    updated_at: "2026-04-17T08:00:00.000Z",
    last_run: {
      agent_fqn: "risk:archived-monitor",
      aggregate_score: 0.51,
      completed_at: "2026-04-17T08:30:00.000Z",
    },
  },
];

describe("EvalSuiteDataTable", () => {
  it("renders rows and forwards create, filter, and row actions", () => {
    const onCreate = vi.fn();
    const onFiltersChange = vi.fn();
    const onRowClick = vi.fn();

    renderWithProviders(
      <EvalSuiteDataTable
        data={evalSuites}
        filters={{ page: 1, search: "", status: "all" }}
        onCreate={onCreate}
        onFiltersChange={onFiltersChange}
        onRowClick={onRowClick}
        totalCount={evalSuites.length}
      />,
    );

    expect(screen.getByText("KYC Agent Quality")).toBeInTheDocument();
    expect(screen.getByText("risk:kyc-agent")).toBeInTheDocument();
    expect(screen.getByText("92%")).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText("Search eval suites"), {
      target: { value: "safety" },
    });
    expect(onFiltersChange).toHaveBeenCalledWith({ page: 1, search: "safety" });

    fireEvent.change(screen.getByLabelText("Filter eval suites by status"), {
      target: { value: "archived" },
    });
    expect(onFiltersChange).toHaveBeenCalledWith({
      page: 1,
      status: "archived",
    });

    fireEvent.click(screen.getByText("risk:archived-monitor"));
    expect(onRowClick).toHaveBeenCalledWith("eval-suite-2");

    fireEvent.click(screen.getByRole("button", { name: "Create Eval Suite" }));
    expect(onCreate).toHaveBeenCalledTimes(1);
  });
});

describe("CreateEvalSuiteForm", () => {
  beforeEach(() => {
    mutationMocks.createEvalSet.mockReset();
    mutationMocks.addCase.mockReset();
    mutationMocks.createEvalSet.mockResolvedValue({ id: "eval-suite-new" });
    mutationMocks.addCase.mockResolvedValue({ id: "case-1" });
  });

  it("validates required fields and submits the suite with benchmark cases", async () => {
    const onSuccess = vi.fn();

    renderWithProviders(
      <CreateEvalSuiteForm
        onSuccess={onSuccess}
        workspaceId="workspace-1"
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: "Create Eval Suite" }));

    expect(await screen.findByText("Name is required.")).toBeInTheDocument();
    expect(await screen.findByText("Prompt is required.")).toBeInTheDocument();
    expect(
      await screen.findByText("Expected output is required."),
    ).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText("Name"), {
      target: { value: "KYC Benchmark" },
    });
    fireEvent.change(screen.getByLabelText("Description"), {
      target: { value: "Baseline suite" },
    });
    fireEvent.change(screen.getByLabelText("Input prompt"), {
      target: { value: "What should the agent do with missing identity data?" },
    });
    fireEvent.change(screen.getByLabelText("Expected output"), {
      target: { value: "Escalate to manual review with a clear explanation." },
    });

    fireEvent.click(screen.getByRole("button", { name: "Create Eval Suite" }));

    await waitFor(() => {
      expect(mutationMocks.createEvalSet).toHaveBeenCalledWith({
        workspace_id: "workspace-1",
        name: "KYC Benchmark",
        description: "Baseline suite",
        pass_threshold: 0.7,
        scorer_config: {},
      });
    });

    expect(mutationMocks.addCase).toHaveBeenCalledWith({
      evalSetId: "eval-suite-new",
      payload: {
        expected_output: "Escalate to manual review with a clear explanation.",
        input_data: {
          input_prompt: "What should the agent do with missing identity data?",
          prompt: "What should the agent do with missing identity data?",
        },
        position: 0,
      },
    });

    await waitFor(() => {
      expect(onSuccess).toHaveBeenCalledWith("eval-suite-new");
    });
  });
});
