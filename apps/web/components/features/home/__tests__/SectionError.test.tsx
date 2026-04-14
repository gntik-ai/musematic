import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { SectionError } from "@/components/features/home/SectionError";

describe("SectionError", () => {
  it("renders the default copy without a retry action", () => {
    render(<SectionError />);

    expect(screen.getByText("Section unavailable")).toBeInTheDocument();
    expect(
      screen.getByText("This section could not be loaded right now."),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: /retry/i }),
    ).not.toBeInTheDocument();
  });

  it("renders a retry button when a handler is provided", async () => {
    const user = userEvent.setup();
    const onRetry = vi.fn();

    render(
      <SectionError
        title="Recent activity unavailable"
        message="Retry the request."
        onRetry={onRetry}
      />,
    );

    await user.click(screen.getByRole("button", { name: /retry/i }));

    expect(onRetry).toHaveBeenCalledTimes(1);
  });
});
