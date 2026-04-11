import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { ConnectionIndicator } from "@/components/layout/header/ConnectionIndicator";

const state = {
  current: "connected",
};

vi.mock("@/components/providers/WebSocketProvider", () => ({
  useWebSocket: () => ({
    connectionState: state.current,
    connect: vi.fn(),
    onStateChange: (handler: (nextState: typeof state.current) => void) => {
      handler(state.current);
      return () => undefined;
    },
  }),
}));

describe("ConnectionIndicator", () => {
  it("renders a reconnecting label when needed", () => {
    state.current = "reconnecting";
    render(<ConnectionIndicator />);
    expect(screen.getByText("Reconnecting...")).toBeInTheDocument();
  });

  it("renders disconnected state with retry action", () => {
    state.current = "disconnected";
    render(<ConnectionIndicator />);
    expect(screen.getByText("disconnected")).toBeInTheDocument();
    expect(screen.getByText("Retry")).toBeInTheDocument();
  });
});
