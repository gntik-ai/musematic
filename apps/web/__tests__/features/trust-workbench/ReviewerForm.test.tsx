import { fireEvent, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ReviewerForm } from "@/components/features/trust-workbench/ReviewerForm";
import { renderWithProviders } from "@/test-utils/render";
import { seedTrustWorkbenchStores } from "@/__tests__/features/trust-workbench/test-helpers";

const toast = vi.fn();
const approveMutateAsync = vi.fn();
const revokeMutateAsync = vi.fn();

vi.mock("@/lib/hooks/use-toast", () => ({
  useToast: () => ({ toast }),
}));

vi.mock("@/lib/hooks/use-certification-actions", () => ({
  useApproveCertification: () => ({
    isPending: false,
    mutateAsync: approveMutateAsync,
  }),
  useRevokeCertification: () => ({
    isPending: false,
    mutateAsync: revokeMutateAsync,
  }),
}));

describe("ReviewerForm", () => {
  beforeEach(() => {
    toast.mockReset();
    approveMutateAsync.mockReset();
    revokeMutateAsync.mockReset();
    seedTrustWorkbenchStores();
  });

  it("requires a decision and review notes before submitting", async () => {
    renderWithProviders(
      <ReviewerForm
        agentId="agent-1"
        certificationId="cert-1"
        currentStatus="pending"
        isExpired={false}
        onDecisionSubmitted={vi.fn()}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: "Submit review" }));

    expect(await screen.findByText("Select a decision.")).toBeInTheDocument();
    expect(await screen.findByText("Review notes are required.")).toBeInTheDocument();
  });

  it("submits approve and reject decisions with the expected payloads", async () => {
    const onDecisionSubmitted = vi.fn();
    approveMutateAsync.mockResolvedValue({});
    revokeMutateAsync.mockResolvedValue({});

    const { rerender } = renderWithProviders(
      <ReviewerForm
        agentId="agent-1"
        certificationId="cert-1"
        currentStatus="pending"
        isExpired={false}
        onDecisionSubmitted={onDecisionSubmitted}
      />,
    );

    fireEvent.click(screen.getByLabelText("Approve"));
    fireEvent.change(screen.getByLabelText("Review notes"), {
      target: { value: "Approve after reviewing the behavioral evidence." },
    });
    fireEvent.change(screen.getByLabelText(/upload pdf, png, or jpg files/i), {
      target: {
        files: [new File(["pdf"], "evidence.pdf", { type: "application/pdf" })],
      },
    });
    fireEvent.click(screen.getByRole("button", { name: "Approve certification" }));

    await waitFor(() => {
      expect(approveMutateAsync).toHaveBeenCalledWith(
        expect.objectContaining({
          certificationId: "cert-1",
          notes: "Approve after reviewing the behavioral evidence.",
          files: expect.arrayContaining([
            expect.objectContaining({ name: "evidence.pdf" }),
          ]),
        }),
      );
    });

    rerender(
      <ReviewerForm
        agentId="agent-1"
        certificationId="cert-1"
        currentStatus="pending"
        isExpired={false}
        onDecisionSubmitted={onDecisionSubmitted}
      />,
    );

    fireEvent.click(screen.getByLabelText("Reject"));
    fireEvent.change(screen.getByLabelText("Review notes"), {
      target: { value: "Reject until privacy remediation is completed." },
    });
    fireEvent.click(screen.getByRole("button", { name: "Reject certification" }));

    await waitFor(() => {
      expect(revokeMutateAsync).toHaveBeenCalledWith({
        certificationId: "cert-1",
        notes: "Reject until privacy remediation is completed.",
      });
    });
    expect(onDecisionSubmitted).toHaveBeenCalled();
  });

  it("surfaces conflict errors and oversized files", async () => {
    approveMutateAsync.mockRejectedValue({
      conflictError: true,
      message: "Conflict",
    });

    renderWithProviders(
      <ReviewerForm
        agentId="agent-1"
        certificationId="cert-1"
        currentStatus="pending"
        isExpired={false}
        onDecisionSubmitted={vi.fn()}
      />,
    );

    fireEvent.click(screen.getByLabelText("Approve"));
    fireEvent.change(screen.getByLabelText("Review notes"), {
      target: { value: "Approve after remediation review." },
    });
    fireEvent.click(screen.getByRole("button", { name: "Approve certification" }));

    expect(
      await screen.findByText("A decision has already been recorded - please refresh"),
    ).toBeInTheDocument();

    const oversizedFile = new File(
      [new Uint8Array(10 * 1024 * 1024 + 1)],
      "oversized.pdf",
      { type: "application/pdf" },
    );
    fireEvent.change(screen.getByLabelText(/upload pdf, png, or jpg files/i), {
      target: { files: [oversizedFile] },
    });
    fireEvent.click(screen.getByRole("button", { name: "Approve certification" }));

    expect(
      await screen.findByText("Each file must be 10MB or smaller."),
    ).toBeInTheDocument();
  });
});
