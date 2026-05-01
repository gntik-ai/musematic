import { fireEvent, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { PlatformStatusBanner } from "@/components/features/platform-status/PlatformStatusBanner";
import { renderWithProviders } from "@/test-utils/render";
import type * as PlatformStatusHook from "@/lib/hooks/use-platform-status";
import type { MyPlatformStatus } from "@/lib/hooks/use-platform-status";

let currentStatus: MyPlatformStatus | undefined;
let pathname = "/home";

vi.mock("next/navigation", () => ({
  usePathname: () => pathname,
}));

vi.mock("@/lib/hooks/use-platform-status", async () => {
  const actual = await vi.importActual<typeof PlatformStatusHook>(
    "@/lib/hooks/use-platform-status",
  );
  return {
    ...actual,
    usePlatformStatus: () => ({
      data: currentStatus,
      isConnected: true,
      isLoading: false,
      lastUpdatedAt: new Date("2026-05-01T12:00:00.000Z"),
    }),
  };
});

function status(overrides: Partial<MyPlatformStatus>): MyPlatformStatus {
  return {
    overall_state: "operational",
    active_maintenance: null,
    active_incidents: [],
    ...overrides,
  };
}

describe("PlatformStatusBanner", () => {
  beforeEach(() => {
    pathname = "/home";
    currentStatus = undefined;
    sessionStorage.clear();
  });

  it("renders scheduled and active maintenance variants", () => {
    currentStatus = status({
      overall_state: "maintenance",
      active_maintenance: {
        window_id: "mw-1",
        title: "Database upgrade",
        starts_at: "2099-05-01T12:00:00.000Z",
        ends_at: "2099-05-01T13:00:00.000Z",
        blocks_writes: true,
        components_affected: ["control-plane-api"],
        affects_my_features: [],
      },
    });

    const view = renderWithProviders(<PlatformStatusBanner />);
    expect(screen.getAllByText("Scheduled maintenance").length).toBeGreaterThan(0);

    currentStatus = status({
      overall_state: "maintenance",
      active_maintenance: {
        window_id: "mw-2",
        title: "Database upgrade",
        starts_at: "2000-05-01T12:00:00.000Z",
        ends_at: "2099-05-01T13:00:00.000Z",
        blocks_writes: true,
        components_affected: ["control-plane-api"],
        affects_my_features: [],
      },
    });

    view.rerender(<PlatformStatusBanner />);
    expect(screen.getByText("Maintenance in progress")).toBeInTheDocument();
  });

  it("renders incident and degraded variants", () => {
    currentStatus = status({
      overall_state: "degraded",
      active_incidents: [
        {
          id: "incident-1",
          title: "Elevated errors",
          severity: "warning",
          started_at: "2026-05-01T12:00:00.000Z",
          resolved_at: null,
          components_affected: ["control-plane-api"],
          last_update_at: "2026-05-01T12:01:00.000Z",
          last_update_summary: "Investigating",
          affects_my_features: [],
        },
      ],
    });

    const view = renderWithProviders(<PlatformStatusBanner />);
    expect(screen.getByText("Active incident")).toBeInTheDocument();
    expect(screen.getByText("Warning")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "View incident" })).toHaveAttribute(
      "href",
      "https://status.musematic.ai/incidents/incident-1",
    );

    currentStatus = status({
      overall_state: "degraded",
      active_incidents: [
        {
          id: "incident-1",
          title: "Elevated errors",
          severity: "critical",
          started_at: "2026-05-01T12:00:00.000Z",
          resolved_at: null,
          components_affected: ["control-plane-api"],
          last_update_at: "2026-05-01T12:03:00.000Z",
          last_update_summary: "Escalated",
          affects_my_features: [],
        },
      ],
    });

    view.rerender(<PlatformStatusBanner />);
    expect(screen.getByText("Critical")).toBeInTheDocument();

    currentStatus = status({ overall_state: "degraded" });
    view.rerender(<PlatformStatusBanner />);
    expect(screen.getAllByText("Degraded").length).toBeGreaterThan(0);
  });

  it("dismisses for the current route and resurfaces on navigation", () => {
    currentStatus = status({ overall_state: "degraded" });

    const view = renderWithProviders(<PlatformStatusBanner />);
    expect(screen.getByTestId("platform-status-banner")).toBeInTheDocument();

    fireEvent.click(screen.getByLabelText("Dismiss"));
    expect(screen.queryByTestId("platform-status-banner")).not.toBeInTheDocument();

    pathname = "/marketplace";
    view.rerender(<PlatformStatusBanner />);
    expect(screen.getByTestId("platform-status-banner")).toBeInTheDocument();
  });
});
