import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { AdminTabPlaceholder } from "@/components/features/admin/tabs/AdminTabPlaceholder";
import { UserActionDialog } from "@/components/features/admin/users/UserActionDialog";
import type { AdminUserRow } from "@/lib/types/admin";
import { renderWithProviders } from "@/test-utils/render";

const adminUser: AdminUserRow = {
  id: "user-1",
  email: "alex@musematic.dev",
  name: "Alex Mercer",
  role: "workspace_admin",
  status: "pending_approval",
  created_at: "2026-04-12T09:00:00.000Z",
  last_login_at: null,
  available_actions: ["approve", "reject"],
};

describe("admin shared admin components", () => {
  it("renders the placeholder title and description", () => {
    renderWithProviders(
      <AdminTabPlaceholder
        description="Coming soon for the next admin milestone."
        title="Future settings"
      />,
    );

    expect(screen.getByText("Future settings")).toBeInTheDocument();
    expect(
      screen.getByText("Coming soon for the next admin milestone."),
    ).toBeInTheDocument();
  });

  it("renders destructive and pending dialog states, and hides itself without a user/action", async () => {
    const user = userEvent.setup();
    const onConfirm = vi.fn();
    const onOpenChange = vi.fn();
    const { rerender } = renderWithProviders(
      <UserActionDialog
        action={null}
        isPending={false}
        open
        user={null}
        onConfirm={onConfirm}
        onOpenChange={onOpenChange}
      />,
    );

    expect(screen.queryByRole("alertdialog")).not.toBeInTheDocument();

    rerender(
      <UserActionDialog
        action="reject"
        isPending={true}
        open
        user={adminUser}
        onConfirm={onConfirm}
        onOpenChange={onOpenChange}
      />,
    );

    expect(screen.getByText("Block account and send rejection email")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Processing/i })).toBeDisabled();

    rerender(
      <UserActionDialog
        action="reactivate"
        isPending={false}
        open
        user={{ ...adminUser, status: "suspended", available_actions: ["reactivate"] }}
        onConfirm={onConfirm}
        onOpenChange={onOpenChange}
      />,
    );

    await user.click(screen.getByRole("button", { name: "Cancel" }));
    await user.click(screen.getByRole("button", { name: "Reactivate user" }));

    expect(onOpenChange).toHaveBeenCalledWith(false);
    expect(onConfirm).toHaveBeenCalled();
  });
});
