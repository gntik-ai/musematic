import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { UsersTab } from "@/components/features/admin/tabs/UsersTab";
import { renderWithProviders } from "@/test-utils/render";
import { setPlatformAdminUser } from "@/tests/features/admin/test-helpers";
import { server } from "@/vitest.setup";

const toast = vi.fn();

vi.mock("@/lib/hooks/use-toast", () => ({
  useToast: () => ({ toast }),
}));

describe("UsersTab", () => {
  beforeEach(() => {
    toast.mockReset();
    setPlatformAdminUser();
  });

  it("renders the table and debounces search/filter changes", async () => {
    renderWithProviders(<UsersTab />);

    expect(await screen.findByText("John Example")).toBeInTheDocument();
    expect(screen.getByText("Riley Ops")).toBeInTheDocument();
    expect(screen.getAllByText("Never")).toHaveLength(2);

    fireEvent.change(screen.getByLabelText("Search users by name or email"), {
      target: { value: "john@example.com" },
    });

    expect(screen.getByText("Riley Ops")).toBeInTheDocument();

    await waitFor(() => {
      expect(screen.queryByText("Riley Ops")).not.toBeInTheDocument();
    }, { timeout: 1500 });

    fireEvent.change(screen.getByLabelText("Filter users by status"), {
      target: { value: "pending_approval" },
    });

    await waitFor(() => {
      expect(screen.getByText("John Example")).toBeInTheDocument();
    }, { timeout: 1500 });
  });

  it("approves a pending user through the dialog and updates the row", async () => {
    const user = userEvent.setup();

    renderWithProviders(<UsersTab />);

    expect(await screen.findByText("John Example")).toBeInTheDocument();

    await user.click(screen.getByLabelText("Open actions for John Example"));
    await user.click(screen.getByRole("button", { name: "Approve John Example" }));

    expect(screen.getByText("Grant platform access")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Approve user" }));

    await waitFor(() => {
      const row = screen.getByText("John Example").closest("tr");
      expect(row).not.toBeNull();
      expect(within(row as HTMLTableRowElement).getByLabelText("status active")).toBeInTheDocument();
    });

    expect(toast).toHaveBeenCalledWith(
      expect.objectContaining({
        title: "John Example updated",
        variant: "success",
      }),
    );
  });

  it("prevents self-suspension in the actions menu", async () => {
    const user = userEvent.setup();

    renderWithProviders(<UsersTab />);

    expect(await screen.findByText("Pat Admin")).toBeInTheDocument();

    await user.click(screen.getByLabelText("Open actions for Pat Admin"));

    expect(
      screen.getByRole("button", { name: "Suspend Pat Admin" }),
    ).toBeDisabled();
  });

  it("closes the dialog without mutating state when the action is cancelled", async () => {
    const user = userEvent.setup();

    renderWithProviders(<UsersTab />);

    expect(await screen.findByText("John Example")).toBeInTheDocument();
    await user.click(screen.getByLabelText("Open actions for John Example"));
    await user.click(screen.getByRole("button", { name: "Approve John Example" }));

    expect(screen.getByText("Grant platform access")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Cancel" }));

    await waitFor(() => {
      expect(screen.queryByText("Grant platform access")).not.toBeInTheDocument();
    });
  });

  it("shows a destructive toast when a user action fails", async () => {
    const user = userEvent.setup();

    server.use(
      http.post("*/api/v1/admin/users/:id/approve", () =>
        HttpResponse.json(
          {
            error: {
              code: "USER_ACTION_FAILED",
              message: "Approval service unavailable",
            },
          },
          { status: 500 },
        ),
      ),
    );

    renderWithProviders(<UsersTab />);

    expect(await screen.findByText("John Example")).toBeInTheDocument();
    await user.click(screen.getByLabelText("Open actions for John Example"));
    await user.click(screen.getByRole("button", { name: "Approve John Example" }));
    await user.click(screen.getByRole("button", { name: "Approve user" }));

    await waitFor(() => {
      expect(toast).toHaveBeenCalledWith(
        expect.objectContaining({
          title: "Approval service unavailable",
          variant: "destructive",
        }),
      );
    });
  });
});
