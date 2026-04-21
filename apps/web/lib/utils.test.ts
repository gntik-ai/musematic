import { afterEach, describe, expect, it, vi } from "vitest";
import { cn, getInitials, sleep, toTitleCase } from "@/lib/utils";

describe("utils", () => {
  afterEach(() => {
    vi.useRealTimers();
  });

  it("merges class names and drops falsy values", () => {
    expect(cn("px-2 py-1", undefined, false, "px-4", "text-sm")).toBe("py-1 px-4 text-sm");
  });

  it("resolves sleep after the requested delay", async () => {
    vi.useFakeTimers();

    let resolved = false;
    const sleeper = sleep(250).then(() => {
      resolved = true;
    });

    await vi.advanceTimersByTimeAsync(249);
    expect(resolved).toBe(false);

    await vi.advanceTimersByTimeAsync(1);
    await sleeper;

    expect(resolved).toBe(true);
  });

  it("converts dashed and underscored values to title case", () => {
    expect(toTitleCase("trajectory_judge-score")).toBe("Trajectory Judge Score");
  });

  it("returns up to two initials from trimmed words", () => {
    expect(getInitials("alex mercer operator")).toBe("AM");
    expect(getInitials("single")).toBe("S");
    expect(getInitials("   ")).toBe("");
  });
});
