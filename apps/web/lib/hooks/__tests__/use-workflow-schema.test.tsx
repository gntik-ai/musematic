import { renderHook, waitFor } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { createHookWrapper } from "@/lib/hooks/__tests__/test-utils";
import { useWorkflowSchema } from "@/lib/hooks/use-workflow-schema";

describe("useWorkflowSchema", () => {
  it("loads the workflow JSON schema with a one-hour stale time", async () => {
    const { Wrapper } = createHookWrapper();
    const { result } = renderHook(() => useWorkflowSchema(), {
      wrapper: Wrapper,
    });

    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });

    expect(result.current.data).toMatchObject({
      $schema: "https://json-schema.org/draft/2020-12/schema",
      required: ["name", "steps"],
    });
  });
});
