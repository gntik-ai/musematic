import { createElement } from "react";
import { act, render, renderHook } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { useAutoScroll } from "@/lib/hooks/use-auto-scroll";
import { useConversationStore } from "@/lib/stores/conversation-store";

describe("useAutoScroll", () => {
  beforeEach(() => {
    useConversationStore.getState().reset();
  });

  it("returns sentinel and container refs", () => {
    const { result } = renderHook(() => useAutoScroll());

    expect(result.current.sentinelRef).toBeDefined();
    expect(result.current.containerRef).toBeDefined();
  });

  it("scrollToBottom re-enables auto scroll and clears pending count", () => {
    useConversationStore.setState({
      autoScrollEnabled: false,
      pendingMessageCount: 3,
    });

    const { result } = renderHook(() => useAutoScroll());
    const scrollIntoView = vi.fn();
    result.current.sentinelRef.current = { scrollIntoView } as unknown as HTMLDivElement;

    act(() => {
      result.current.scrollToBottom();
    });

    expect(scrollIntoView).toHaveBeenCalled();
    expect(useConversationStore.getState().autoScrollEnabled).toBe(true);
    expect(useConversationStore.getState().pendingMessageCount).toBe(0);
  });

  it("reacts to intersection changes by toggling auto scroll state", () => {
    let observerCallback:
      | ((entries: Array<{ isIntersecting: boolean }>) => void)
      | undefined;

    vi.stubGlobal(
      "IntersectionObserver",
      vi.fn().mockImplementation((callback: typeof observerCallback) => {
        observerCallback = callback;
        return {
          disconnect: vi.fn(),
          observe: vi.fn(),
        };
      }),
    );

    function Harness() {
      const { containerRef, sentinelRef } = useAutoScroll();
      return createElement(
        "div",
        { ref: containerRef },
        createElement("div", { ref: sentinelRef }),
      );
    }

    render(createElement(Harness));

    act(() => {
      observerCallback?.([{ isIntersecting: false }]);
    });
    expect(useConversationStore.getState().autoScrollEnabled).toBe(false);

    useConversationStore.setState({
      ...useConversationStore.getState(),
      pendingMessageCount: 2,
    });

    act(() => {
      observerCallback?.([{ isIntersecting: true }]);
    });
    expect(useConversationStore.getState().autoScrollEnabled).toBe(true);
    expect(useConversationStore.getState().pendingMessageCount).toBe(0);
  });
});
