import * as React from "react";
import { act, fireEvent, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { AgentUploadZone } from "@/components/features/agent-management/AgentUploadZone";
import { renderWithProviders } from "@/test-utils/render";
import { seedAgentManagementStores } from "@/__tests__/features/agent-management/test-helpers";

const navigationMocks = vi.hoisted(() => ({
  navigateToAgentDetail: vi.fn(),
}));

const toast = vi.fn();
const abort = vi.fn();
const mutateAsync = vi.fn();
let setUploadState: React.Dispatch<
  React.SetStateAction<{ isPending: boolean; progress: number; validationErrors: string[] }>
>;

vi.mock("@/lib/hooks/use-toast", () => ({
  useToast: () => ({ toast }),
}));

vi.mock("@/lib/agent-management/navigation", () => ({
  navigateToAgentDetail: navigationMocks.navigateToAgentDetail,
}));

vi.mock("@/lib/hooks/use-agent-upload", async () => {
  const ReactModule = await vi.importActual("react");

  class UploadValidationError extends Error {
    validationErrors: string[];

    constructor(message: string, validationErrors: string[]) {
      super(message);
      this.validationErrors = validationErrors;
    }
  }

  return {
    UploadValidationError,
    useUploadAgentPackage: () => {
      const [state, setState] = (ReactModule as typeof React).useState({
        isPending: false,
        progress: 0,
        validationErrors: [] as string[],
      });
      setUploadState = setState;

      return {
        ...state,
        abort,
        mutateAsync,
      };
    },
  };
});

describe("AgentUploadZone", () => {
  beforeEach(() => {
    toast.mockReset();
    abort.mockReset();
    mutateAsync.mockReset();
    navigationMocks.navigateToAgentDetail.mockReset();
    seedAgentManagementStores();
  });

  it("rejects invalid files before upload", async () => {
    renderWithProviders(
      <AgentUploadZone onUploadComplete={vi.fn()} workspace_id="workspace-1" />,
    );

    fireEvent.change(screen.getByLabelText(/select package/i), {
      target: {
        files: [new File(["bad"], "bad.txt", { type: "text/plain" })],
      },
    });

    expect(
      await screen.findByText(
        "Unsupported file type. Only .tar.gz and .zip files are accepted.",
      ),
    ).toBeInTheDocument();
  });

  it("shows upload progress, completes successfully, and supports cancellation", async () => {
    const onUploadComplete = vi.fn();
    let resolveUpload: ((value: { agent_fqn: string; status: "draft"; validation_errors: string[] }) => void) | undefined;

    mutateAsync.mockImplementation(
      () =>
        new Promise((resolve) => {
          resolveUpload = resolve;
          setUploadState({
            isPending: true,
            progress: 0,
            validationErrors: [],
          });
        }),
    );

    renderWithProviders(
      <AgentUploadZone onUploadComplete={onUploadComplete} workspace_id="workspace-1" />,
    );

    fireEvent.change(screen.getByLabelText(/select package/i), {
      target: {
        files: [
          new File(["good"], "agent.tar.gz", {
            type: "application/gzip",
          }),
        ],
      },
    });

    await screen.findByText("Uploading package…");

    act(() => {
      setUploadState({
        isPending: true,
        progress: 50,
        validationErrors: [],
      });
    });

    expect(await screen.findByText("50%")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /cancel upload/i }));
    expect(abort).toHaveBeenCalled();

    act(() => {
      setUploadState({
        isPending: false,
        progress: 100,
        validationErrors: [],
      });
      resolveUpload?.({
        agent_fqn: "risk:kyc-monitor",
        status: "draft",
        validation_errors: [],
      });
    });

    await waitFor(() => {
      expect(onUploadComplete).toHaveBeenCalledWith("risk:kyc-monitor");
    });
    expect(navigationMocks.navigateToAgentDetail).toHaveBeenCalledWith(
      "risk:kyc-monitor",
    );
  });

  it("renders server validation errors from a 422 response", async () => {
    const { UploadValidationError } = await import("@/lib/hooks/use-agent-upload");

    mutateAsync.mockImplementation(async () => {
      setUploadState({
        isPending: false,
        progress: 0,
        validationErrors: ["missing agent.yaml"],
      });
      throw new UploadValidationError("Validation failed", ["missing agent.yaml"]);
    });

    renderWithProviders(
      <AgentUploadZone onUploadComplete={vi.fn()} workspace_id="workspace-1" />,
    );

    fireEvent.change(screen.getByLabelText(/select package/i), {
      target: {
        files: [
          new File(["good"], "agent.tar.gz", {
            type: "application/gzip",
          }),
        ],
      },
    });

    expect(await screen.findByText("missing agent.yaml")).toBeInTheDocument();
  });
});
