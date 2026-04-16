import { fireEvent, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { AgentPublicationPanel } from "@/components/features/agent-management/AgentPublicationPanel";
import { renderWithProviders } from "@/test-utils/render";
import { ApiError } from "@/types/api";
import { sampleValidationResult, seedAgentManagementStores } from "@/__tests__/features/agent-management/test-helpers";

const toast = vi.fn();
const validateMutateAsync = vi.fn();
const publishMutateAsync = vi.fn();

vi.mock("@/lib/hooks/use-toast", () => ({
  useToast: () => ({ toast }),
}));

vi.mock("@/lib/hooks/use-agent-mutations", () => ({
  useValidateAgent: () => ({
    isPending: false,
    mutateAsync: validateMutateAsync,
  }),
  usePublishAgent: () => ({
    isPending: false,
    mutateAsync: publishMutateAsync,
  }),
}));

describe("AgentPublicationPanel", () => {
  beforeEach(() => {
    toast.mockReset();
    validateMutateAsync.mockReset();
    publishMutateAsync.mockReset();
    seedAgentManagementStores();
  });

  it("requires validation before publish and confirms before calling publish", async () => {
    const onPublished = vi.fn();
    validateMutateAsync.mockResolvedValue(sampleValidationResult);
    publishMutateAsync.mockResolvedValue({
      fqn: "risk:kyc-monitor",
      previous_status: "draft",
      new_status: "active",
      affected_workspaces: ["Risk Ops"],
      published_at: "2026-04-16T12:00:00.000Z",
    });

    renderWithProviders(
      <AgentPublicationPanel
        currentStatus="draft"
        fqn="risk:kyc-monitor"
        onPublished={onPublished}
      />,
    );

    expect(screen.getByRole("button", { name: "Publish" })).toBeDisabled();

    fireEvent.click(screen.getByRole("button", { name: "Validate" }));

    expect(await screen.findByText("Schema")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Publish" })).toBeEnabled();

    fireEvent.click(screen.getByRole("button", { name: "Publish" }));

    expect(await screen.findByText("Publish agent?")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Confirm publish" }));

    await waitFor(() => {
      expect(publishMutateAsync).toHaveBeenCalledWith("risk:kyc-monitor");
    });
    expect(onPublished).toHaveBeenCalled();
  });

  it("shows a destructive toast when publish fails with a conflict", async () => {
    validateMutateAsync.mockResolvedValue(sampleValidationResult);
    publishMutateAsync.mockRejectedValue(
      new ApiError("conflict", "Validation no longer passes", 409),
    );

    renderWithProviders(
      <AgentPublicationPanel
        currentStatus="draft"
        fqn="risk:kyc-monitor"
        onPublished={vi.fn()}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: "Validate" }));
    fireEvent.click(await screen.findByRole("button", { name: "Publish" }));
    fireEvent.click(await screen.findByRole("button", { name: "Confirm publish" }));

    await waitFor(() => {
      expect(toast).toHaveBeenCalledWith(
        expect.objectContaining({
          title: "Validation no longer passes",
          variant: "destructive",
        }),
      );
    });
  });
});

