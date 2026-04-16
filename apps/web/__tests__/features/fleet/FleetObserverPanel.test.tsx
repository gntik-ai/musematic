import { fireEvent, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { FleetObserverPanel } from "@/components/features/fleet/FleetObserverPanel";
import { renderWithProviders } from "@/test-utils/render";
import {
  sampleFindings,
  seedFleetStores,
} from "@/__tests__/features/fleet/test-helpers";

const acknowledgeMutation = {
  isPending: false,
  mutateAsync: vi.fn().mockResolvedValue(undefined),
};
const observerHookMock = vi.fn();

vi.mock("@/lib/hooks/use-observer-findings", () => ({
  useObserverFindings: (fleetId: string, filters: { severity: string | null; acknowledged: boolean | null }) => {
    observerHookMock(fleetId, filters);
    const items = sampleFindings.filter((finding) => {
      if (filters.severity && finding.severity !== filters.severity) {
        return false;
      }
      if (filters.acknowledged === false) {
        return !finding.acknowledged;
      }
      return true;
    });
    return {
      data: {
        items,
      },
    };
  },
  useAcknowledgeFinding: () => acknowledgeMutation,
}));

describe("FleetObserverPanel", () => {
  beforeEach(() => {
    observerHookMock.mockClear();
    acknowledgeMutation.mutateAsync.mockClear();
    seedFleetStores();
  });

  it("filters findings by severity and acknowledges open findings", () => {
    renderWithProviders(<FleetObserverPanel fleetId="fleet-1" />);

    expect(screen.getByText(/Latency spike detected/i)).toBeInTheDocument();
    expect(screen.queryByText(/Observer confidence baseline recalculated/i)).not.toBeInTheDocument();

    fireEvent.change(screen.getByLabelText("Finding severity"), {
      target: { value: "critical" },
    });
    expect(observerHookMock).toHaveBeenLastCalledWith("fleet-1", {
      acknowledged: false,
      limit: 100,
      severity: "critical",
    });

    fireEvent.click(screen.getByRole("button", { name: /acknowledge finding finding-1/i }));
    expect(acknowledgeMutation.mutateAsync).toHaveBeenCalledWith({
      fleetId: "fleet-1",
      findingId: "finding-1",
    });

    fireEvent.click(screen.getByRole("switch"));
    expect(screen.getByText("Acknowledged")).toBeInTheDocument();
  });
});
