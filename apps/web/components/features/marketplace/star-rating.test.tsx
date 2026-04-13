import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { StarRating } from "@/components/features/marketplace/star-rating";

describe("StarRating", () => {
  it("renders a no-ratings state", () => {
    render(<StarRating rating={null} />);

    expect(screen.getByText("No ratings")).toBeInTheDocument();
  });

  it("renders a numeric rating and review count", () => {
    render(<StarRating rating={4.3} reviewCount={12} />);

    expect(screen.getByText("4.3")).toBeInTheDocument();
    expect(screen.getByText("(12 reviews)")).toBeInTheDocument();
  });
});
