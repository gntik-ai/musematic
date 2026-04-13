import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { FilterSidebar } from "@/components/features/marketplace/filter-sidebar";

const filterMetadata = {
  capabilities: ["financial_analysis", "identity_verification"],
  tags: ["finance", "risk"],
};

describe("FilterSidebar", () => {
  it("renders the desktop filter groups inline", () => {
    render(
      <FilterSidebar
        activeFilterCount={1}
        filterMetadata={filterMetadata}
        filters={{ maturityLevels: ["production"] }}
        isMobile={false}
        onChange={vi.fn()}
      />,
    );

    expect(
      screen.getByRole("navigation", { name: "Agent filters" }),
    ).toBeInTheDocument();
    expect(screen.getByText("Maturity level")).toBeInTheDocument();
    expect(screen.getByText("Capabilities")).toBeInTheDocument();
  });

  it("opens the mobile sheet when triggered", async () => {
    const user = userEvent.setup();

    render(
      <FilterSidebar
        activeFilterCount={2}
        filterMetadata={filterMetadata}
        filters={{}}
        isMobile
        onChange={vi.fn()}
      />,
    );

    await user.click(screen.getByRole("button", { name: /filters \(2\)/i }));

    expect(screen.getByRole("dialog")).toBeInTheDocument();
    expect(screen.getByText("Agent filters")).toBeInTheDocument();
  });
});
