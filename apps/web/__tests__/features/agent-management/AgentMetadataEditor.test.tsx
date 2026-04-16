import { fireEvent, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { AgentMetadataEditor } from "@/components/features/agent-management/AgentMetadataEditor";
import { renderWithProviders } from "@/test-utils/render";
import { ApiError } from "@/types/api";
import { sampleAgent, seedAgentManagementStores } from "@/__tests__/features/agent-management/test-helpers";

const toast = vi.fn();
const mutateAsync = vi.fn();
const refetch = vi.fn();

vi.mock("@/lib/hooks/use-toast", () => ({
  useToast: () => ({ toast }),
}));

vi.mock("@/lib/hooks/use-agents", () => ({
  useAgent: () => ({
    data: sampleAgent,
    refetch,
  }),
}));

vi.mock("@/lib/hooks/use-agent-mutations", () => ({
  useUpdateAgentMetadata: () => ({
    isPending: false,
    mutateAsync,
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

describe("AgentMetadataEditor", () => {
  beforeEach(() => {
    toast.mockReset();
    mutateAsync.mockReset();
    refetch.mockReset();
    seedAgentManagementStores();
  });

  it("validates purpose and local name, updates the FQN preview, and saves successfully", async () => {
    const onSaved = vi.fn();
    mutateAsync.mockResolvedValue(sampleAgent);

    renderWithProviders(<AgentMetadataEditor fqn={sampleAgent.fqn} onSaved={onSaved} />);

    fireEvent.change(screen.getByLabelText("Purpose"), {
      target: { value: "" },
    });

    expect(
      await screen.findByText("Purpose must be at least 20 characters"),
    ).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText("Local name"), {
      target: { value: "INVALID_NAME" },
    });

    expect(
      await screen.findByText("Lowercase alphanumeric and hyphens only"),
    ).toBeInTheDocument();

    const namespaceSelect = screen.getByLabelText("Namespace") as HTMLSelectElement;
    fireEvent.change(namespaceSelect, {
      target: { value: "ops" },
    });
    fireEvent.change(screen.getByLabelText("Local name"), {
      target: { value: "fraud-sentinel" },
    });

    expect(screen.getByText("Preview: ops:fraud-sentinel")).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText("Purpose"), {
      target: {
        value:
          "Monitor transaction anomalies, route cases, and keep the fraud team informed.",
      },
    });

    fireEvent.click(screen.getByRole("button", { name: "Save metadata" }));

    await waitFor(() => {
      expect(mutateAsync).toHaveBeenCalled();
    });
    expect(onSaved).toHaveBeenCalled();
  });

  it("shows a stale data alert on a 412 response", async () => {
    mutateAsync.mockRejectedValue(
      new ApiError("stale", "Stale data", 412),
    );

    renderWithProviders(<AgentMetadataEditor fqn={sampleAgent.fqn} />);

    fireEvent.click(screen.getByRole("button", { name: "Save metadata" }));

    expect(
      await screen.findByText("Stale settings detected"),
    ).toBeInTheDocument();
  });
});

