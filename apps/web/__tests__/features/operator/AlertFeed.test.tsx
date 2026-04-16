import { act, fireEvent, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { AlertFeed } from "@/components/features/operator/AlertFeed";
import { useAlertFeedStore } from "@/lib/stores/use-alert-feed-store";
import { renderWithProviders } from "@/test-utils/render";
import {
  sampleAlerts,
  seedOperatorStores,
} from "@/__tests__/features/operator/test-helpers";

vi.mock("@/lib/hooks/use-alert-feed", () => ({
  useAlertFeed: vi.fn(),
}));

describe("AlertFeed", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-04-16T12:00:00.000Z"));
    seedOperatorStores();
    useAlertFeedStore.setState({
      alerts: sampleAlerts,
      severityFilter: "all",
      isConnected: true,
    });
  });

  it("renders alerts, filters by severity, expands details, and resumes auto-scroll from the new alerts affordance", () => {
    const { container } = renderWithProviders(<AlertFeed maxHeight="200px" />);

    expect(
      screen.getByText("Consumer lag rising on orchestration topic."),
    ).toBeInTheDocument();
    expect(screen.getByText("Query latency breached SLO.")).toBeInTheDocument();
    expect(screen.getByText("Execution admission paused.")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Error" }));
    expect(screen.getByText("Query latency breached SLO.")).toBeInTheDocument();
    expect(
      screen.queryByText("Consumer lag rising on orchestration topic."),
    ).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "All" }));
    fireEvent.click(screen.getByText("Execution admission paused."));
    expect(
      screen.getByText(
        "The runtime controller rejected new workloads after repeated faults.",
      ),
    ).toBeInTheDocument();
    expect(
      screen.getByText("Review the most recent deployment and drain the queue."),
    ).toBeInTheDocument();

    const scrollRegion = container.querySelector(
      '[style*="max-height: 200px"]',
    ) as HTMLDivElement;
    Object.defineProperty(scrollRegion, "scrollHeight", {
      configurable: true,
      value: 800,
    });
    Object.defineProperty(scrollRegion, "clientHeight", {
      configurable: true,
      value: 200,
    });
    Object.defineProperty(scrollRegion, "scrollTop", {
      configurable: true,
      writable: true,
      value: 120,
    });

    fireEvent.scroll(scrollRegion);
    expect(
      screen.getByRole("button", { name: "New alerts ↓" }),
    ).toBeInTheDocument();

    act(() => {
      useAlertFeedStore.getState().addAlert({
        id: "alert-4",
        severity: "info",
        sourceService: "redis",
        timestamp: "2026-04-16T12:00:01.000Z",
        message: "Cache hit ratio recovered.",
        description: null,
        suggestedAction: null,
      });
    });

    expect(screen.getByRole("button", { name: "New alerts ↓" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "New alerts ↓" }));
    expect(
      screen.queryByRole("button", { name: "New alerts ↓" }),
    ).not.toBeInTheDocument();
  });
});
