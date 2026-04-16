import { fireEvent, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { CertificationDataTable } from "@/components/features/trust-workbench/CertificationDataTable";
import { renderWithProviders } from "@/test-utils/render";
import {
  sampleCertificationQueue,
  seedTrustWorkbenchStores,
} from "@/__tests__/features/trust-workbench/test-helpers";
import { DEFAULT_CERTIFICATION_QUEUE_FILTERS } from "@/lib/types/trust-workbench";

describe("CertificationDataTable", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    seedTrustWorkbenchStores();
  });

  it("renders queue rows and updates search, tabs, pagination, and row navigation", () => {
    const onFiltersChange = vi.fn();
    const onRowClick = vi.fn();

    renderWithProviders(
      <CertificationDataTable
        data={sampleCertificationQueue}
        filters={DEFAULT_CERTIFICATION_QUEUE_FILTERS}
        isLoading={false}
        onFiltersChange={onFiltersChange}
        onRowClick={onRowClick}
        totalCount={42}
      />,
    );

    expect(screen.getByText("Fraud Monitor")).toBeInTheDocument();
    expect(screen.getByText("KYC Review")).toBeInTheDocument();
    expect(screen.getByText("42 certifications in view")).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText("Search certifications"), {
      target: { value: "fraud" },
    });
    vi.advanceTimersByTime(300);
    expect(onFiltersChange).toHaveBeenLastCalledWith(
      expect.objectContaining({ search: "fraud", page: 1 }),
    );

    fireEvent.click(screen.getByRole("button", { name: "Pending" }));
    expect(onFiltersChange).toHaveBeenLastCalledWith({ status: "pending", page: 1 });

    fireEvent.change(screen.getByLabelText("Page size"), {
      target: { value: "50" },
    });
    expect(onFiltersChange).toHaveBeenLastCalledWith({ page: 1, page_size: 50 });

    fireEvent.click(screen.getByRole("button", { name: /Next/i }));
    expect(onFiltersChange).toHaveBeenLastCalledWith({ page: 2 });

    fireEvent.click(screen.getByText("Fraud Monitor"));
    expect(onRowClick).toHaveBeenCalledWith("cert-1");
  });

  it("renders an empty state when the queue has no rows", () => {
    renderWithProviders(
      <CertificationDataTable
        data={[]}
        filters={DEFAULT_CERTIFICATION_QUEUE_FILTERS}
        isLoading={false}
        onFiltersChange={vi.fn()}
        onRowClick={vi.fn()}
        totalCount={0}
      />,
    );

    expect(
      screen.getByText("No certifications match the active filters."),
    ).toBeInTheDocument();
  });
});
