import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { ConnectionStatusBanner } from "@/components/features/home/ConnectionStatusBanner";

describe("ConnectionStatusBanner", () => {
  it("renders nothing when the websocket is connected", () => {
    const { container } = render(<ConnectionStatusBanner isConnected />);
    expect(container).toBeEmptyDOMElement();
  });

  it("renders an accessible status banner when disconnected", () => {
    render(<ConnectionStatusBanner isConnected={false} />);

    expect(screen.getByRole("status")).toHaveAttribute("aria-live", "polite");
    expect(
      screen.getByText("Live updates paused — reconnecting…"),
    ).toBeInTheDocument();
  });
});
