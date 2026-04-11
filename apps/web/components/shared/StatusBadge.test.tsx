import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { StatusBadge } from "@/components/shared/StatusBadge";

describe("StatusBadge", () => {
  it("renders default label mappings", () => {
    render(<StatusBadge status="healthy" />);
    expect(screen.getByLabelText("status healthy")).toBeInTheDocument();
  });

  it("accepts custom labels", () => {
    render(<StatusBadge label="Live now" status="running" />);
    expect(screen.getByText("Live now")).toBeInTheDocument();
  });
});
