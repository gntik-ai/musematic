import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { ErrorBoundary } from "@/components/features/home/ErrorBoundary";

function ThrowingChild(): React.JSX.Element {
  throw new Error("boom");
}

describe("ErrorBoundary", () => {
  it("renders the fallback when a child throws", () => {
    const spy = vi.spyOn(console, "error").mockImplementation(() => {});

    render(
      <ErrorBoundary fallback={<div>Fallback content</div>}>
        <ThrowingChild />
      </ErrorBoundary>,
    );

    expect(screen.getByText("Fallback content")).toBeInTheDocument();
    spy.mockRestore();
  });

  it("resets after the resetKey changes", () => {
    const spy = vi.spyOn(console, "error").mockImplementation(() => {});

    const { rerender } = render(
      <ErrorBoundary fallback={<div>Fallback content</div>} resetKey="first">
        <ThrowingChild />
      </ErrorBoundary>,
    );

    expect(screen.getByText("Fallback content")).toBeInTheDocument();

    rerender(
      <ErrorBoundary fallback={<div>Fallback content</div>} resetKey="second">
        <div>Recovered content</div>
      </ErrorBoundary>,
    );

    expect(screen.getByText("Recovered content")).toBeInTheDocument();
    spy.mockRestore();
  });
});
