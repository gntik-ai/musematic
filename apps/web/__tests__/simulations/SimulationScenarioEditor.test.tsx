import { fireEvent, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { SimulationScenarioEditor } from "@/components/features/simulations/SimulationScenarioEditor";
import { renderWithProviders } from "@/test-utils/render";

const hookMocks = vi.hoisted(() => ({
  createScenario: vi.fn(),
  updateScenario: vi.fn(),
}));

vi.mock("@/lib/hooks/use-simulation-scenarios", () => ({
  useScenario: () => ({ data: undefined, isLoading: false }),
  useCreateScenario: () => ({
    mutateAsync: hookMocks.createScenario,
    isPending: false,
  }),
  useUpdateScenario: () => ({
    mutateAsync: hookMocks.updateScenario,
    isPending: false,
  }),
}));

describe("SimulationScenarioEditor", () => {
  beforeEach(() => {
    hookMocks.createScenario.mockReset();
    hookMocks.updateScenario.mockReset();
    hookMocks.createScenario.mockImplementation(async (payload) => ({
      ...payload,
      id: "scenario-1",
      archived_at: null,
      created_by: "user-1",
      created_at: "2026-05-01T10:00:00.000Z",
      updated_at: "2026-05-01T10:00:00.000Z",
    }));
  });

  it("uses mock LLM defaults and submits a valid scenario payload", async () => {
    const user = userEvent.setup();
    renderWithProviders(
      <SimulationScenarioEditor mode="create" workspaceId="workspace-1" />,
    );

    expect((screen.getByLabelText("Mock set") as HTMLTextAreaElement).value).toContain(
      '"llm_provider": "mock-llm"',
    );

    await user.type(screen.getByLabelText("Name"), "Checkout regression");
    await user.type(screen.getByLabelText("Agents"), "ops:triage, risk:analyst");
    await user.click(screen.getByRole("button", { name: "Create Scenario" }));

    await waitFor(() => {
      expect(hookMocks.createScenario).toHaveBeenCalledWith(
        expect.objectContaining({
          workspace_id: "workspace-1",
          name: "Checkout regression",
          agents_config: { agents: ["ops:triage", "risk:analyst"] },
          mock_set_config: { llm_provider: "mock-llm" },
        }),
      );
    });
  });

  it("blocks plaintext secrets before submitting", async () => {
    const user = userEvent.setup();
    renderWithProviders(
      <SimulationScenarioEditor mode="create" workspaceId="workspace-1" />,
    );

    await user.type(screen.getByLabelText("Name"), "Secret regression");
    await user.type(screen.getByLabelText("Agents"), "ops:triage");
    await user.clear(screen.getByLabelText("Mock set"));
    fireEvent.change(screen.getByLabelText("Mock set"), {
      target: { value: '{"api_key":"sk-abcdefghijklmnop"}' },
    });
    await user.click(screen.getByRole("button", { name: "Create Scenario" }));

    expect(
      await screen.findByText("Plaintext secrets are not allowed in scenario configuration."),
    ).toBeInTheDocument();
    expect(hookMocks.createScenario).not.toHaveBeenCalled();
  });

  it("requires explicit USE_REAL_LLM confirmation for real LLM preview", async () => {
    const user = userEvent.setup();
    renderWithProviders(
      <SimulationScenarioEditor mode="create" workspaceId="workspace-1" />,
    );

    await user.click(screen.getByRole("button", { name: "Real LLM Preview" }));
    expect(screen.getByText("Confirm Real LLM Preview")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Confirm" })).toBeDisabled();

    await user.type(screen.getByPlaceholderText("USE_REAL_LLM"), "USE_REAL_LLM");
    await user.click(screen.getByRole("button", { name: "Confirm" }));

    expect(screen.getByText("Real LLM preview confirmed")).toBeInTheDocument();
  });
});
