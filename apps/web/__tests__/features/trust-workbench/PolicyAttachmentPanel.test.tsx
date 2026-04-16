import { fireEvent, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { PolicyAttachmentPanel } from "@/components/features/trust-workbench/PolicyAttachmentPanel";
import { renderWithProviders } from "@/test-utils/render";
import {
  samplePolicyBindings,
  samplePolicyCatalog,
  seedTrustWorkbenchStores,
} from "@/__tests__/features/trust-workbench/test-helpers";
import { usePolicyAttachmentStore } from "@/lib/stores/use-policy-attachment-store";

const toast = vi.fn();
const attachMutateAsync = vi.fn();
const detachMutateAsync = vi.fn();

vi.mock("@/lib/hooks/use-toast", () => ({
  useToast: () => ({ toast }),
}));

vi.mock("@/lib/hooks/use-policy-catalog", () => ({
  usePolicyCatalog: () => ({
    data: { items: samplePolicyCatalog },
    isFetching: false,
    isLoading: false,
  }),
}));

vi.mock("@/lib/hooks/use-effective-policies", () => ({
  useEffectivePolicies: () => ({
    data: samplePolicyBindings,
    isLoading: false,
  }),
}));

vi.mock("@/lib/hooks/use-policy-actions", () => ({
  useAttachPolicy: () => ({
    mutateAsync: attachMutateAsync,
  }),
  useDetachPolicy: () => ({
    mutateAsync: detachMutateAsync,
  }),
}));

describe("PolicyAttachmentPanel", () => {
  beforeEach(() => {
    toast.mockReset();
    attachMutateAsync.mockReset();
    detachMutateAsync.mockReset();
    usePolicyAttachmentStore.setState({
      isDragging: false,
      draggedPolicyId: null,
      draggedPolicyName: null,
      dropError: null,
    });
    seedTrustWorkbenchStores();
  });

  it("renders policy cards, supports drag-and-drop attach, and protects duplicate attachments", async () => {
    attachMutateAsync.mockResolvedValue({});

    renderWithProviders(
      <PolicyAttachmentPanel
        agentId="agent-1"
        agentRevisionId="rev-1"
        workspaceId="workspace-1"
      />,
    );

    const draggableCard = screen
      .getByText("Fraud triage policy")
      .closest("[draggable='true']");
    expect(draggableCard).toHaveAttribute("draggable", "true");

    const dataTransfer = {
      data: new Map<string, string>(),
      getData(key: string) {
        return this.data.get(key) ?? "";
      },
      setData(key: string, value: string) {
        this.data.set(key, value);
      },
    };

    fireEvent.dragStart(draggableCard as Element, { dataTransfer });
    fireEvent.dragOver(screen.getByText(/effective bindings/i).closest("div") as Element, {
      dataTransfer,
    });
    fireEvent.drop(screen.getByText(/effective bindings/i).closest("div") as Element, {
      dataTransfer,
    });

    await waitFor(() => {
      expect(attachMutateAsync).toHaveBeenCalledWith({
        policyId: "policy-new",
        agentId: "agent-1",
        agentRevisionId: "rev-1",
      });
    });

    fireEvent.click(screen.getAllByRole("button", { name: /Attach/i })[0]!);
    expect(
      await screen.findByText(/already attached to the selected revision/i),
    ).toBeInTheDocument();
  });

  it("shows direct and inherited bindings, and confirms direct removal", async () => {
    detachMutateAsync.mockResolvedValue(undefined);

    renderWithProviders(
      <PolicyAttachmentPanel
        agentId="agent-1"
        agentRevisionId="rev-1"
        workspaceId="workspace-1"
      />,
    );

    expect(screen.getAllByText("Direct review guardrail")).toHaveLength(2);
    expect(screen.getByRole("link", { name: /Manage ->/i })).toHaveAttribute(
      "href",
      "/fleet/fleet-1",
    );

    fireEvent.click(screen.getByRole("button", { name: "Remove" }));
    expect(
      screen.getByRole("alertdialog", { name: "" }),
    ).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Remove policy" }));

    await waitFor(() => {
      expect(detachMutateAsync).toHaveBeenCalledWith({
        attachmentId: "attachment-direct",
        policyId: "policy-direct",
        agentId: "agent-1",
      });
    });
  });
});
