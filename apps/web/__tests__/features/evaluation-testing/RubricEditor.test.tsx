import { fireEvent, screen, waitFor } from "@testing-library/react";
import React from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { CalibrationBoxplot } from "@/components/features/evaluation/calibration-boxplot";
import { RubricEditor } from "@/components/features/evaluation/rubric-editor";
import { TrajectoryComparisonSelector } from "@/components/features/evaluation/trajectory-comparison-selector";
import { renderWithProviders } from "@/test-utils/render";
import { useAuthStore } from "@/store/auth-store";
import { useWorkspaceStore } from "@/store/workspace-store";

const saveRubricSpy = vi.fn();
const rubricState = {
  rubric: {
    id: "rubric-1",
    name: "Trajectory quality rubric",
    description: "Score the trajectory.",
    comparisonMethod: "exact_match" as const,
    dimensions: [
      { id: "accuracy", name: "Accuracy", description: "Correctness", weight: 0.5, scaleType: "numeric_1_5" as const, categoricalValues: null },
      { id: "fluency", name: "Fluency", description: "Clarity", weight: 0.3, scaleType: "numeric_1_5" as const, categoricalValues: null },
      { id: "safety", name: "Safety", description: "Risk handling", weight: 0.2, scaleType: "numeric_1_5" as const, categoricalValues: null },
    ],
  },
  isLoading: false,
  saveRubric: {
    isPending: false,
    mutateAsync: saveRubricSpy,
  },
};

const calibrationState = {
  isLoading: false,
  scores: [
    {
      dimensionId: "safety",
      dimensionName: "Safety",
      distribution: { min: 1, q1: 2, median: 3, q3: 4, max: 5 },
      kappa: 0.52,
      isOutlier: true,
    },
  ],
};

vi.mock("recharts", () => ({
  ResponsiveContainer: ({ children }: { children: React.ReactNode }) => (
    <div data-testid="responsive-container">{children}</div>
  ),
  ComposedChart: ({ children }: { children: React.ReactNode }) => <svg>{children}</svg>,
  CartesianGrid: () => null,
  Tooltip: () => null,
  XAxis: ({ dataKey }: { dataKey?: string }) => <g data-testid={`x-axis-${dataKey ?? "unknown"}`} />,
  YAxis: () => <g data-testid="y-axis" />,
  ReferenceLine: () => null,
  Scatter: ({ dataKey, fill, children }: { dataKey?: string; fill?: string; children?: React.ReactNode }) => (
    <g data-testid={`scatter-${dataKey ?? "unknown"}`} data-fill={fill}>{children}</g>
  ),
  LabelList: ({ dataKey }: { dataKey?: string }) => <text>{dataKey === "kappaLabel" ? "κ = 0.52" : "3"}</text>,
}));

vi.mock("@/lib/hooks/use-rubric-editor", () => ({
  useRubricEditor: () => rubricState,
}));

vi.mock("@/lib/hooks/use-calibration-scores", () => ({
  useCalibrationScores: () => calibrationState,
}));

describe("evaluation feature expansions", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    useAuthStore.setState({
      accessToken: "access-token",
      refreshToken: "refresh-token",
      isAuthenticated: true,
      user: {
        id: "user-1",
        email: "owner@musematic.dev",
        displayName: "Owner",
        avatarUrl: null,
        mfaEnrolled: true,
        roles: ["workspace_admin"],
        workspaceId: "workspace-1",
      },
    } as never);
    useWorkspaceStore.setState({
      currentWorkspace: {
        id: "workspace-1",
        name: "Risk Ops",
        slug: "risk-ops",
        description: "Workspace",
        memberCount: 8,
        createdAt: "2026-04-10T09:00:00.000Z",
      },
      sidebarCollapsed: false,
      workspaceList: [],
      isLoading: false,
    } as never);
  });

  it("debounces weight validation and gates save until the total returns to 1.00", async () => {
    renderWithProviders(<RubricEditor suiteId="suite-1" />);

    await waitFor(() => expect(screen.getByText(/Weight sum: 1\.00/)).toBeInTheDocument());

    const firstWeight = screen.getByLabelText("Dimension weight accuracy");
    fireEvent.change(firstWeight, { target: { value: "0.6" } });

    await waitFor(() => expect(screen.getByText(/Weight sum: 1\.10/)).toBeInTheDocument());
    expect(screen.getByRole("button", { name: "Save rubric" })).toBeDisabled();

    fireEvent.change(firstWeight, { target: { value: "0.5" } });

    await waitFor(() => expect(screen.getByText(/Weight sum: 1\.00/)).toBeInTheDocument());
    const saveButton = screen.getByRole("button", { name: "Save rubric" });
    expect(saveButton).toBeEnabled();

    fireEvent.click(saveButton);

    await waitFor(() => expect(saveRubricSpy).toHaveBeenCalledTimes(1));
    expect(saveRubricSpy).toHaveBeenCalledWith(
      expect.objectContaining({ comparisonMethod: "exact_match" }),
    );
  });

  it("renders the calibration outlier annotation for low-kappa dimensions", () => {
    renderWithProviders(<CalibrationBoxplot suiteId="suite-1" />);

    expect(screen.getByText("Calibration box plot")).toBeInTheDocument();
    expect(screen.getByText("κ = 0.52")).toBeInTheDocument();
    expect(screen.getByTestId("scatter-outlier")).toBeInTheDocument();
  });

  it("updates the comparison description when the selected method changes", () => {
    const onChange = vi.fn();
    renderWithProviders(
      <TrajectoryComparisonSelector value="exact_match" onChange={onChange} />,
    );

    expect(
      screen.getByText(/Strictly compare generated outputs against the benchmark response\./),
    ).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText("Comparison method"), {
      target: { value: "semantic_similarity" },
    });

    expect(onChange).toHaveBeenCalledWith("semantic_similarity");
  });
});
