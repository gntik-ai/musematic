import { act, renderHook, waitFor } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { createHookWrapper } from "@/lib/hooks/__tests__/test-utils";
import { useExecutionJournal } from "@/lib/hooks/use-execution-journal";

describe("useExecutionJournal", () => {
  it("loads filtered journal pages and paginates by offset", async () => {
    const { Wrapper } = createHookWrapper();
    const { result } = renderHook(
      () =>
        useExecutionJournal("execution-1", {
          eventType: "REASONING_TRACE_EMITTED",
          stepId: "evaluate_risk",
          limit: 1,
        }),
      {
        wrapper: Wrapper,
      },
    );

    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });

    expect(result.current.data?.pages[0]).toMatchObject({
      offset: 0,
      limit: 1,
      hasNext: false,
      items: [
        expect.objectContaining({
          eventType: "REASONING_TRACE_EMITTED",
          stepId: "evaluate_risk",
        }),
      ],
    });

    await act(async () => {
      await result.current.fetchNextPage();
    });

    expect(result.current.data?.pages).toHaveLength(1);
  });

  it("stays idle when there is no execution id", () => {
    const { Wrapper } = createHookWrapper();
    const { result } = renderHook(() => useExecutionJournal(null), {
      wrapper: Wrapper,
    });

    expect(result.current.fetchStatus).toBe("idle");
    expect(result.current.data).toBeUndefined();
  });

  it("adds since-sequence filters when requesting incremental journal updates", async () => {
    const { Wrapper } = createHookWrapper();
    const { result } = renderHook(
      () =>
        useExecutionJournal("execution-1", {
          sinceSequence: 3,
          limit: 10,
        }),
      {
        wrapper: Wrapper,
      },
    );

    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });

    expect(result.current.data?.pages[0]?.items[0]).toMatchObject({
      sequence: 3,
    });
  });

  it("honors an explicit disabled flag", () => {
    const { Wrapper } = createHookWrapper();
    const { result } = renderHook(
      () =>
        useExecutionJournal("execution-1", {
          enabled: false,
        }),
      {
        wrapper: Wrapper,
      },
    );

    expect(result.current.fetchStatus).toBe("idle");
  });

  it("uses the default limit and omits optional filters when none are supplied", async () => {
    const { Wrapper } = createHookWrapper();
    const { result } = renderHook(
      () =>
        useExecutionJournal("execution-1", {
          stepId: null,
        }),
      {
        wrapper: Wrapper,
      },
    );

    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });

    expect(result.current.data?.pages[0]).toMatchObject({
      offset: 0,
      limit: 50,
      hasNext: false,
    });
    expect(result.current.data?.pages[0]?.items.length).toBeGreaterThan(1);
  });
});
