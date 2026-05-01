import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { StatusBanner } from "./StatusBanner";

describe("StatusBanner", () => {
  it.each([
    ["operational", "Operational", "border-emerald-300"],
    ["degraded", "Degraded performance", "border-amber-300"],
    ["partial_outage", "Partial outage", "border-orange-300"],
    ["full_outage", "Full outage", "border-red-300"],
    ["maintenance", "Maintenance", "border-sky-300"],
  ] as const)("renders %s with color, icon, and text", (state, label, className) => {
    render(<StatusBanner state={state} label={label} detail="Current platform state" />);

    const region = screen.getByRole("region");
    expect(region).toHaveAttribute("aria-live", "polite");
    expect(region).toHaveClass(className);
    expect(screen.getAllByText(label).length).toBeGreaterThan(0);
    expect(screen.getByText("Current platform state")).toBeInTheDocument();
    expect(region.querySelector("svg")).not.toBeNull();
  });
});
