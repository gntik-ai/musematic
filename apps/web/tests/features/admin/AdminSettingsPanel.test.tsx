import { fireEvent, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import AdminLayout from "@/app/(main)/admin/layout";
import { AdminSettingsPanel } from "@/components/features/admin/AdminSettingsPanel";
import { renderWithProviders } from "@/test-utils/render";
import { setNonAdminUser, setPlatformAdminUser } from "@/tests/features/admin/test-helpers";

const push = vi.fn();
const replace = vi.fn();
const toast = vi.fn();

vi.mock("next/navigation", () => ({
  usePathname: () => "/admin/settings",
  useRouter: () => ({ push, replace }),
}));

vi.mock("@/lib/hooks/use-toast", () => ({
  useToast: () => ({ toast }),
}));

describe("AdminSettingsPanel", () => {
  beforeEach(() => {
    push.mockReset();
    replace.mockReset();
    toast.mockReset();
    setPlatformAdminUser();
  });

  it("renders all tab triggers and activates the tab from the URL", async () => {
    renderWithProviders(<AdminSettingsPanel defaultTab="signup" />);

    expect(screen.getByText("Users")).toBeInTheDocument();
    expect(screen.getByText("Signup")).toBeInTheDocument();
    expect(screen.getByText("Quotas")).toBeInTheDocument();
    expect(screen.getByText("Connectors")).toBeInTheDocument();
    expect(screen.getByText("Email")).toBeInTheDocument();
    expect(screen.getByText("Security")).toBeInTheDocument();
    expect(await screen.findByText("Signup policy")).toBeInTheDocument();
  });

  it("updates the URL when the user switches tabs", () => {
    renderWithProviders(<AdminSettingsPanel defaultTab="users" />);

    fireEvent.click(screen.getByRole("button", { name: "Security" }));

    expect(push).toHaveBeenCalledWith("/admin/settings?tab=security");
  });

  it("redirects non-admin users from the admin layout", async () => {
    setNonAdminUser();

    renderWithProviders(
      <AdminLayout>
        <div>Restricted content</div>
      </AdminLayout>,
    );

    await waitFor(() => {
      expect(replace).toHaveBeenCalledWith("/home");
    });
    expect(toast).toHaveBeenCalledWith(
      expect.objectContaining({
        title: "You do not have permission to access admin settings",
        variant: "destructive",
      }),
    );
  });
});
