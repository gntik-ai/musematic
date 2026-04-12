import { act, renderHook } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { useAutoScroll } from "@/lib/hooks/use-auto-scroll";
import { useConversationStore } from "@/lib/stores/conversation-store";

describe("useAutoScroll", () => {
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
});
