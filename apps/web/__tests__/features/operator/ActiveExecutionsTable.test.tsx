import { act, fireEvent, screen } from "@testing-library/react";
import { useState } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ActiveExecutionsTable } from "@/components/features/operator/ActiveExecutionsTable";
import { renderWithProviders } from "@/test-utils/render";
import {
  sampleActiveExecutions,
  seedOperatorStores,
} from "@/__tests__/features/operator/test-helpers";
import {
  DEFAULT_ACTIVE_EXECUTIONS_FILTERS,
  type ActiveExecutionsFilters,
} from "@/lib/types/operator-dashboard";

const toastMocks = vi.hoisted(() => ({
  toast: vi.fn(),
}));

vi.mock("@/lib/hooks/use-toast", () => ({
  useToast: () => toastMocks,
}));

function Harness({
  onRowClick,
}: {
  onRowClick: (executionId: string) => void;
}) {
  const [filters, setFilters] = useState<ActiveExecutionsFilters>(
    DEFAULT_ACTIVE_EXECUTIONS_FILTERS,
  );

  return (
    <ActiveExecutionsTable
      executions={sampleActiveExecutions}
      filters={filters}
      isLoading={false}
      onFiltersChange={(next) =>
        setFilters((current) => ({ ...current, ...next }))
      }
      onRowClick={onRowClick}
      totalCount={sampleActiveExecutions.length}
    />
  );
}

describe("ActiveExecutionsTable", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-04-16T12:00:00.000Z"));
    seedOperatorStores();
    toastMocks.toast.mockReset();
    vi.mocked(navigator.clipboard.writeText).mockClear();
  });

  it("renders all columns, updates filters and sorting, ticks elapsed time, and handles row actions", async () => {
    const onRowClick = vi.fn();
    const { container } = renderWithProviders(
      <Harness onRowClick={onRowClick} />,
    );

    expect(screen.getByText("Execution")).toBeInTheDocument();
    expect(screen.getByText("Agent")).toBeInTheDocument();
    expect(screen.getByText("Workflow")).toBeInTheDocument();
    expect(screen.getByText("Current step")).toBeInTheDocument();
    expect(screen.getAllByText("Status")).toHaveLength(2);
    expect(screen.getAllByText("Started")).toHaveLength(2);
    expect(screen.getAllByText("Elapsed")).toHaveLength(2);
    expect(screen.getByText("Fraud triage")).toBeInTheDocument();
    expect(screen.getByText("Identity review")).toBeInTheDocument();
    expect(screen.getByText("Chargeback recovery")).toBeInTheDocument();
    expect(screen.getByText("00:02:00")).toBeInTheDocument();

    act(() => {
      vi.advanceTimersByTime(1000);
    });
    expect(screen.getByText(/00:02:01/)).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText("Execution status filter"), {
      target: { value: "paused" },
    });
    expect(screen.getByText("Identity review")).toBeInTheDocument();
    expect(screen.queryByText("Fraud triage")).not.toBeInTheDocument();

    fireEvent.change(screen.getByLabelText("Execution status filter"), {
      target: { value: "all" },
    });
    fireEvent.change(screen.getByLabelText("Execution sort order"), {
      target: { value: "elapsed" },
    });

    const rows = Array.from(container.querySelectorAll("tbody tr"));
    expect(rows[0]).toHaveTextContent("Identity review");
    expect(rows[1]).toHaveTextContent("Fraud triage");

    fireEvent.click(
      screen.getByRole("button", {
        name: "Copy execution id exec-run-0001",
      }),
    );
    expect(navigator.clipboard.writeText).toHaveBeenCalledWith("exec-run-0001");
    await act(async () => {
      await Promise.resolve();
    });
    expect(toastMocks.toast).toHaveBeenCalledWith(
      expect.objectContaining({
        title: "Execution id copied",
        variant: "success",
      }),
    );

    fireEvent.click(screen.getByLabelText("Open execution exec-run-0001"));
    expect(onRowClick).toHaveBeenCalledWith("exec-run-0001");
  });
});
