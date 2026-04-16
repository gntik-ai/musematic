import { fireEvent, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { FleetDataTable } from "@/components/features/fleet/FleetDataTable";
import { renderWithProviders } from "@/test-utils/render";
import {
  sampleFleetListEntries,
  seedFleetStores,
} from "@/__tests__/features/fleet/test-helpers";

const navigationMocks = vi.hoisted(() => ({
  push: vi.fn(),
  replace: vi.fn(),
}));

vi.mock("next/navigation", () => ({
  usePathname: () => "/fleet",
  useRouter: () => navigationMocks,
  useSearchParams: () => new URLSearchParams(""),
}));

vi.mock("@/lib/hooks/use-fleets", () => ({
  useFleets: () => ({
    data: {
      items: sampleFleetListEntries,
      total: sampleFleetListEntries.length,
      page: 1,
      size: 20,
    },
    isFetching: false,
    isLoading: false,
  }),
}));

describe("FleetDataTable", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    navigationMocks.push.mockReset();
    navigationMocks.replace.mockReset();
    seedFleetStores();
  });

  it("renders columns, updates filters through the URL, and exposes detail navigation", () => {
    renderWithProviders(<FleetDataTable workspace_id="workspace-1" />);

    expect(screen.getByText("Fleet")).toBeInTheDocument();
    expect(screen.getByText("Fraud mesh")).toBeInTheDocument();
    expect(screen.getByText("KYC review")).toBeInTheDocument();
    expect(screen.getAllByText(/health/i)[0]).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText("Search fleets"), {
      target: { value: "fraud" },
    });
    vi.advanceTimersByTime(300);
    expect(navigationMocks.replace).toHaveBeenCalledWith("/fleet?search=fraud");

    const statusSelect = screen.getByLabelText("Status") as HTMLSelectElement;
    statusSelect.options[1]!.selected = true;
    fireEvent.change(statusSelect);
    expect(navigationMocks.replace).toHaveBeenCalledWith("/fleet?status=degraded");

    const minHealthSelect = screen.getByLabelText("Min health");
    fireEvent.change(minHealthSelect, { target: { value: "70" } });
    expect(navigationMocks.replace).toHaveBeenCalledWith("/fleet?health_min=70");

    expect(screen.getByRole("link", { name: "Fraud mesh" })).toHaveAttribute(
      "href",
      "/fleet/fleet-1",
    );
  });
});
