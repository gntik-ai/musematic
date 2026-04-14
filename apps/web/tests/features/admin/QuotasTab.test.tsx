import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import * as adminHooks from "@/lib/hooks/use-admin-settings";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { QuotasTab } from "@/components/features/admin/tabs/QuotasTab";
import { renderWithProviders } from "@/test-utils/render";
import { setPlatformAdminUser } from "@/tests/features/admin/test-helpers";
import { server } from "@/vitest.setup";

const toast = vi.fn();

vi.mock("@/lib/hooks/use-toast", () => ({
  useToast: () => ({ toast }),
}));

describe("QuotasTab", () => {
  beforeEach(() => {
    toast.mockReset();
    setPlatformAdminUser();
  });

  it("pre-populates default quotas and loads workspace override data from the combobox", async () => {
    const user = userEvent.setup();

    renderWithProviders(<QuotasTab />);

    const maxAgentInputs = await screen.findAllByLabelText("Max agents");
    expect(maxAgentInputs[0]).toHaveValue(100);

    await user.click(
      screen.getByRole("button", { name: "Select workspace override target" }),
    );
    await user.type(screen.getByLabelText("Search workspaces"), "Signal");
    await user.click(screen.getByRole("button", { name: /Signal Lab/i }));

    await waitFor(() => {
      const overrideInputs = screen.getAllByLabelText("Max agents");
      expect(overrideInputs[1]).toHaveValue(250);
    });
  });

  it("sends null fields correctly when saving a workspace override", async () => {
    const user = userEvent.setup();
    let capturedBody: unknown;

    server.use(
      http.patch(
        "*/api/v1/admin/settings/quotas/workspaces/:workspaceId",
        async ({ request }) => {
          capturedBody = await request.json();
          return HttpResponse.json({
            workspace_id: "workspace-1",
            workspace_name: "Signal Lab",
            ...(capturedBody as Record<string, unknown>),
            updated_at: "2026-04-12T12:00:00.000Z",
          });
        },
      ),
    );

    renderWithProviders(<QuotasTab />);

    await user.click(
      screen.getByRole("button", { name: "Select workspace override target" }),
    );
    await user.type(screen.getByLabelText("Search workspaces"), "Signal");
    await user.click(screen.getByRole("button", { name: /Signal Lab/i }));

    await waitFor(() => {
      expect(screen.getAllByLabelText("Max agents")[1]).toHaveValue(250);
    });

    const overrideMaxAgents = screen.getAllByLabelText("Max agents")[1];
    const overrideStorageQuota = screen.getAllByLabelText("Storage quota (GB)")[1];
    if (!overrideMaxAgents || !overrideStorageQuota) {
      throw new Error("Expected workspace override inputs to be present");
    }

    await user.clear(overrideMaxAgents);
    await user.clear(overrideStorageQuota);
    await user.type(overrideStorageQuota, "640");
    const overrideSaveButton = screen.getAllByRole("button", { name: "Save" })[1];
    if (!overrideSaveButton) {
      throw new Error("Expected workspace override save button to be present");
    }

    await user.click(overrideSaveButton);

    await waitFor(() => {
      expect(capturedBody).toEqual(
        expect.objectContaining({
          max_agents: null,
          storage_quota_gb: 640,
        }),
      );
    });
  });

  it("keeps workspace override inputs disabled until a workspace is selected", async () => {
    renderWithProviders(<QuotasTab />);

    const overrideInputs = await screen.findAllByLabelText("Max agents");
    expect(overrideInputs[1]).toBeDisabled();
    expect(screen.getAllByRole("button", { name: "Save" })[1]).toBeDisabled();
  });

  it("reloads the latest default quotas after a stale update conflict", async () => {
    const user = userEvent.setup();

    server.use(
      http.patch("*/api/v1/admin/settings/quotas", () =>
        HttpResponse.json(
          {
            error: {
              code: "stale_data",
              message: "Default quotas changed",
            },
          },
          { status: 412 },
        ),
      ),
    );

    renderWithProviders(<QuotasTab />);

    const maxAgentInputs = await screen.findAllByLabelText("Max agents");
    await user.clear(maxAgentInputs[0]);
    await user.type(maxAgentInputs[0], "120");
    await user.click(screen.getAllByRole("button", { name: "Save" })[0]);

    expect(
      await screen.findByText(/Settings were changed by another administrator/i),
    ).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Reload" }));

    await waitFor(() => {
      expect(screen.getAllByLabelText("Max agents")[0]).toHaveValue(100);
    });
  });

  it("resets default quota edits, saves successfully, and clears the saved state timer", async () => {
    const user = userEvent.setup();

    renderWithProviders(<QuotasTab />);

    const maxAgentInputs = await screen.findAllByLabelText("Max agents");
    await user.clear(maxAgentInputs[0]);
    await user.type(maxAgentInputs[0], "140");
    await user.click(screen.getAllByRole("button", { name: "Reset" })[0]);

    await waitFor(() => {
      expect(screen.getAllByLabelText("Max agents")[0]).toHaveValue(100);
    });

    await user.clear(screen.getAllByLabelText("Max agents")[0]);
    await user.type(screen.getAllByLabelText("Max agents")[0], "155");
    await user.click(screen.getAllByRole("button", { name: "Save" })[0]);

    expect(await screen.findByRole("button", { name: /Saved ✓/i })).toBeInTheDocument();

    await new Promise((resolve) => setTimeout(resolve, 1600));

    await waitFor(() => {
      expect(screen.queryByRole("button", { name: /Saved ✓/i })).not.toBeInTheDocument();
      expect(screen.getAllByRole("button", { name: "Save" })[0]).toBeInTheDocument();
    });
  });

  it("shows a destructive toast when saving default quotas fails", async () => {
    const user = userEvent.setup();

    server.use(
      http.patch("*/api/v1/admin/settings/quotas", () =>
        HttpResponse.json(
          {
            error: {
              code: "DEFAULT_QUOTAS_FAILED",
              message: "Default quotas could not be saved",
            },
          },
          { status: 500 },
        ),
      ),
    );

    renderWithProviders(<QuotasTab />);

    const maxAgentInputs = await screen.findAllByLabelText("Max agents");
    await user.clear(maxAgentInputs[0]);
    await user.type(maxAgentInputs[0], "160");
    await user.click(screen.getAllByRole("button", { name: "Save" })[0]);

    await waitFor(() => {
      expect(toast).toHaveBeenCalledWith(
        expect.objectContaining({
          title: "Default quotas could not be saved",
          variant: "destructive",
        }),
      );
    });
  });

  it("returns early when default quotas are submitted before query data is available", async () => {
    const user = userEvent.setup();
    const mutation = vi.fn();
    const quotasSpy = vi.spyOn(adminHooks, "useDefaultQuotas").mockReturnValue({
      data: undefined,
      refetch: vi.fn(),
    } as never);
    const mutationSpy = vi.spyOn(adminHooks, "useDefaultQuotasMutation").mockReturnValue({
      isPending: false,
      mutateAsync: mutation,
    } as never);

    renderWithProviders(<QuotasTab />);

    const maxAgentInputs = await screen.findAllByLabelText("Max agents");
    await user.clear(maxAgentInputs[0]);
    await user.type(maxAgentInputs[0], "140");
    await user.click(screen.getAllByRole("button", { name: "Save" })[0]);

    expect(mutation).not.toHaveBeenCalled();

    mutationSpy.mockRestore();
    quotasSpy.mockRestore();
  });

  it("falls back to a generic default quota error message for non-API failures", async () => {
    const user = userEvent.setup();
    const mutationSpy = vi.spyOn(adminHooks, "useDefaultQuotasMutation").mockReturnValue({
      isPending: false,
      mutateAsync: vi.fn().mockRejectedValue(new Error("network down")),
    } as never);

    renderWithProviders(<QuotasTab />);

    const maxAgentInputs = await screen.findAllByLabelText("Max agents");
    await user.clear(maxAgentInputs[0]);
    await user.type(maxAgentInputs[0], "170");
    await user.click(screen.getAllByRole("button", { name: "Save" })[0]);

    await waitFor(() => {
      expect(toast).toHaveBeenCalledWith(
        expect.objectContaining({
          title: "Unable to update default quotas",
          variant: "destructive",
        }),
      );
    });

    mutationSpy.mockRestore();
  });

  it("resets workspace override edits and shows API errors through toast", async () => {
    const user = userEvent.setup();

    server.use(
      http.patch("*/api/v1/admin/settings/quotas/workspaces/:workspaceId", () =>
        HttpResponse.json(
          {
            error: {
              code: "QUOTA_OVERRIDE_FAILED",
              message: "Workspace override could not be persisted",
            },
          },
          { status: 500 },
        ),
      ),
    );

    renderWithProviders(<QuotasTab />);

    await user.click(
      screen.getByRole("button", { name: "Select workspace override target" }),
    );
    await user.type(screen.getByLabelText("Search workspaces"), "Signal");
    await user.click(screen.getByRole("button", { name: /Signal Lab/i }));

    await waitFor(() => {
      expect(screen.getAllByLabelText("Storage quota (GB)")[1]).toHaveValue(null);
    });

    const overrideStorageQuota = screen.getAllByLabelText("Storage quota (GB)")[1];
    await user.type(overrideStorageQuota, "640");
    await user.click(screen.getAllByRole("button", { name: "Reset" })[1]);

    await waitFor(() => {
      expect(screen.getAllByLabelText("Storage quota (GB)")[1]).toHaveValue(null);
    });

    await user.type(screen.getAllByLabelText("Storage quota (GB)")[1], "777");
    await user.click(screen.getAllByRole("button", { name: "Save" })[1]);

    await waitFor(() => {
      expect(toast).toHaveBeenCalledWith(
        expect.objectContaining({
          title: "Workspace override could not be persisted",
          variant: "destructive",
        }),
      );
    });
  });

  it("reloads stale workspace overrides and clears the saved state timer after a successful save", async () => {
    const user = userEvent.setup();
    let firstPatch = true;

    server.use(
      http.patch("*/api/v1/admin/settings/quotas/workspaces/:workspaceId", async ({ request }) => {
        if (firstPatch) {
          firstPatch = false;
          return HttpResponse.json(
            {
              error: {
                code: "stale_data",
                message: "Workspace override changed",
              },
            },
            { status: 412 },
          );
        }

        const body = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json({
          workspace_id: "workspace-1",
          workspace_name: "Signal Lab",
          max_agents: 250,
          max_concurrent_executions: null,
          max_sandboxes: 20,
          monthly_token_budget: body.monthly_token_budget ?? 5000,
          storage_quota_gb: null,
          updated_at: "2026-04-13T12:00:00.000Z",
        });
      }),
    );

    renderWithProviders(<QuotasTab />);

    await user.click(
      screen.getByRole("button", { name: "Select workspace override target" }),
    );
    await user.type(screen.getByLabelText("Search workspaces"), "Signal");
    await user.click(screen.getByRole("button", { name: /Signal Lab/i }));

    await waitFor(() => {
      expect(screen.getAllByLabelText("Monthly token budget")[1]).toHaveValue(5000);
    });

    const monthlyBudget = screen.getAllByLabelText("Monthly token budget")[1];
    await user.clear(monthlyBudget);
    await user.type(monthlyBudget, "6100");
    await user.click(screen.getAllByRole("button", { name: "Save" })[1]);

    expect(
      await screen.findByText(/Settings were changed by another administrator/i),
    ).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Reload" }));
    await waitFor(() => {
      expect(screen.getAllByLabelText("Monthly token budget")[1]).toHaveValue(5000);
    });

    await user.clear(screen.getAllByLabelText("Monthly token budget")[1]);
    await user.type(screen.getAllByLabelText("Monthly token budget")[1], "6200");
    await user.click(screen.getAllByRole("button", { name: "Save" })[1]);

    expect(await screen.findAllByRole("button", { name: /Saved ✓/i })).toHaveLength(1);

    await new Promise((resolve) => setTimeout(resolve, 1600));

    await waitFor(() => {
      expect(screen.queryByRole("button", { name: /Saved ✓/i })).not.toBeInTheDocument();
      expect(screen.getAllByRole("button", { name: "Save" })[1]).toBeInTheDocument();
    });
  });

  it("returns early when workspace override metadata is still loading", async () => {
    const user = userEvent.setup();
    const quotaSpy = vi.spyOn(adminHooks, "useWorkspaceQuota").mockReturnValue({
      data: undefined,
      refetch: vi.fn(),
    } as never);
    const mutation = vi.fn();
    const mutationSpy = vi.spyOn(adminHooks, "useWorkspaceQuotaMutation").mockReturnValue({
      isPending: false,
      mutateAsync: mutation,
    } as never);

    renderWithProviders(<QuotasTab />);

    await user.click(
      screen.getByRole("button", { name: "Select workspace override target" }),
    );
    await user.type(screen.getByLabelText("Search workspaces"), "Signal");
    await user.click(screen.getByRole("button", { name: /Signal Lab/i }));

    const overrideMaxAgents = screen.getAllByLabelText("Max agents")[1];
    await user.type(overrideMaxAgents, "320");
    await user.click(screen.getAllByRole("button", { name: "Save" })[1]);

    expect(mutation).not.toHaveBeenCalled();

    mutationSpy.mockRestore();
    quotaSpy.mockRestore();
  });

  it("falls back to a generic workspace override error message for non-API failures", async () => {
    const user = userEvent.setup();
    const mutationSpy = vi.spyOn(adminHooks, "useWorkspaceQuotaMutation").mockReturnValue({
      isPending: false,
      mutateAsync: vi.fn().mockRejectedValue(new Error("timeout")),
    } as never);

    renderWithProviders(<QuotasTab />);

    await user.click(
      screen.getByRole("button", { name: "Select workspace override target" }),
    );
    await user.type(screen.getByLabelText("Search workspaces"), "Signal");
    await user.click(screen.getByRole("button", { name: /Signal Lab/i }));

    await waitFor(() => {
      expect(screen.getAllByLabelText("Storage quota (GB)")[1]).toBeInTheDocument();
    });

    await user.type(screen.getAllByLabelText("Storage quota (GB)")[1], "900");
    await user.click(screen.getAllByRole("button", { name: "Save" })[1]);

    await waitFor(() => {
      expect(toast).toHaveBeenCalledWith(
        expect.objectContaining({
          title: "Unable to update workspace override",
          variant: "destructive",
        }),
      );
    });

    mutationSpy.mockRestore();
  });
});
