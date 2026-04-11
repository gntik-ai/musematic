import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { UsersTab } from "@/components/features/admin/tabs/UsersTab";
import { renderWithProviders } from "@/test-utils/render";
import { setPlatformAdminUser } from "@/tests/features/admin/test-helpers";

const toast = vi.fn();

vi.mock("@/lib/hooks/use-toast", () => ({
  useToast: () => ({ toast }),
}));

describe("UsersTab", () => {
  beforeEach(() => {
    toast.mockReset();
    setPlatformAdminUser();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("renders the table and debounces search/filter changes", async () => {
    vi.useFakeTimers();
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });

    renderWithProviders(<UsersTab />);

    expect(await screen.findByText("John Example")).toBeInTheDocument();
    expect(screen.getByText("Riley Ops")).toBeInTheDocument();

    await user.type(
      screen.getByLabelText("Search users by name or email"),
      "john@example.com",
    );

    expect(screen.getByText("Riley Ops")).toBeInTheDocument();

    await vi.advanceTimersByTimeAsync(300);

    await waitFor(() => {
      expect(screen.queryByText("Riley Ops")).not.toBeInTheDocument();
    });

    await user.selectOptions(
      screen.getByLabelText("Filter users by status"),
      "pending_approval",
    );

    await waitFor(() => {
      expect(screen.getByText("John Example")).toBeInTheDocument();
    });
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
});
