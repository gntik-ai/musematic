import { act, renderHook } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import {
  clearStream,
  resetStreamState,
  useMessageStream,
} from "@/lib/hooks/use-message-stream";

describe("useMessageStream", () => {
  afterEach(() => {
    resetStreamState();
  });

  it("accumulates deltas and flushes them on animation frame", () => {
    vi.spyOn(window, "requestAnimationFrame").mockImplementation((callback) => {
      callback(16);
      return 1;
    });

    const { result } = renderHook(() => useMessageStream());

    act(() => {
      result.current.addDelta("message-1", "hello ");
      result.current.addDelta("message-1", "world");
    });

    expect(result.current.getStreamingContent("message-1")).toBe("hello world");
  });

  it("clears stream content", () => {
    vi.spyOn(window, "requestAnimationFrame").mockImplementation((callback) => {
      callback(16);
      return 1;
    });

    const { result } = renderHook(() => useMessageStream());

    act(() => {
      result.current.addDelta("message-1", "hello");
    });

    act(() => {
      clearStream("message-1");
    });

    expect(result.current.getStreamingContent("message-1")).toBeUndefined();
  });
});
