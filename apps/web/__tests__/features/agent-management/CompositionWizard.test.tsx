import { fireEvent, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { CompositionWizard } from "@/components/features/agent-management/CompositionWizard";
import { useCompositionWizardStore } from "@/lib/stores/use-composition-wizard-store";
import { renderWithProviders } from "@/test-utils/render";
import { sampleBlueprint, seedAgentManagementStores } from "@/__tests__/features/agent-management/test-helpers";

const push = vi.fn();

vi.mock("next/navigation", async () => {
  const actual = await vi.importActual("next/navigation");

  return {
    ...(actual as object),
    useRouter: () => ({ push }),
  };
});

describe("CompositionWizard", () => {
  beforeEach(() => {
    push.mockReset();
    seedAgentManagementStores();
    useCompositionWizardStore.getState().reset();
  });

  it("renders step 1 initially, advances and regresses through steps, and resets on cancel", () => {
    useCompositionWizardStore.setState({
      blueprint: sampleBlueprint,
      description: sampleBlueprint.description,
      step: 1,
    });

    renderWithProviders(<CompositionWizard />);

    expect(
      screen.getByText("Describe the agent you want to create"),
    ).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Next" }));

    expect(screen.getByText("Review the generated blueprint")).toBeInTheDocument();
    expect(screen.getAllByText("Low confidence recommendation").length).toBeGreaterThan(0);

    fireEvent.click(screen.getByRole("button", { name: "Back" }));

    expect(
      screen.getByText("Describe the agent you want to create"),
    ).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Cancel" }));

    expect(useCompositionWizardStore.getState().step).toBe(1);
    expect(push).toHaveBeenCalledWith("/agent-management");
  });
});
