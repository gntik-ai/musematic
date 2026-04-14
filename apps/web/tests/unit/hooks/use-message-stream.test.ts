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
    let frameCallback: FrameRequestCallback | undefined;
    vi.spyOn(window, "requestAnimationFrame").mockImplementation((callback) => {
      frameCallback = callback;
      return 1;
    });

    const { result } = renderHook(() => useMessageStream());

    act(() => {
      result.current.addDelta("message-1", "hello ");
      result.current.addDelta("message-1", "world");
    });

    act(() => {
      frameCallback?.(16);
    });

    expect(result.current.getStreamingContent("message-1")).toBe("hello world");
  });

  it("clears stream content", () => {
    let frameCallback: FrameRequestCallback | undefined;
    vi.spyOn(window, "requestAnimationFrame").mockImplementation((callback) => {
      frameCallback = callback;
      return 1;
    });

    const { result } = renderHook(() => useMessageStream());

    act(() => {
      result.current.addDelta("message-1", "hello");
    });

    act(() => {
      frameCallback?.(16);
    });

    act(() => {
      clearStream("message-1");
    });

    act(() => {
      frameCallback?.(16);
    });

    expect(result.current.getStreamingContent("message-1")).toBeUndefined();
  });

  it("cancels pending frames when the stream state is reset", () => {
    const cancelSpy = vi.spyOn(window, "cancelAnimationFrame");
    vi.spyOn(window, "requestAnimationFrame").mockImplementation(() => 7);

    const { result } = renderHook(() => useMessageStream());

    act(() => {
      result.current.addDelta("message-1", "queued");
      resetStreamState();
    });

    expect(cancelSpy).toHaveBeenCalledWith(7);
    expect(result.current.streamingContent.size).toBe(0);
  });
});
