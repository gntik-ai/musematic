import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { RevisionDiffViewer } from "@/components/features/agent-management/RevisionDiffViewer";

const useRevisionDiff = vi.fn();

vi.mock("next-themes", () => ({
  useTheme: () => ({ resolvedTheme: "light" }),
}));

vi.mock("@/lib/hooks/use-agent-revisions", () => ({
  useRevisionDiff: (...args: unknown[]) => useRevisionDiff(...args),
}));

vi.mock("@monaco-editor/react", () => ({
  DiffEditor: ({
    modified,
    original,
  }: {
    modified: string;
    original: string;
  }) => <div data-testid="monaco-diff">{original}::{modified}</div>,
}));

vi.mock("next/dynamic", () => ({
  default: () =>
    ({
      modified,
      original,
    }: {
      modified: string;
      original: string;
    }) => <div data-testid="monaco-diff">{original}::{modified}</div>,
}));

describe("RevisionDiffViewer", () => {
  beforeEach(() => {
    useRevisionDiff.mockReset();
  });

  it("shows a skeleton while loading", () => {
    useRevisionDiff.mockReturnValue({
      data: null,
      isLoading: true,
    });

    const { container } = render(
      <RevisionDiffViewer baseRevision={1} compareRevision={2} fqn="risk:kyc-monitor" />,
    );

    expect(container.querySelectorAll(".animate-pulse").length).toBeGreaterThan(0);
  });

  it("renders the diff content when data is available", () => {
    useRevisionDiff.mockReturnValue({
      data: {
        base_content: "name: old",
        compare_content: "name: new",
      },
      isLoading: false,
    });

    render(
      <RevisionDiffViewer baseRevision={1} compareRevision={2} fqn="risk:kyc-monitor" />,
    );

    expect(screen.getByTestId("monaco-diff")).toHaveTextContent(
      "name: old::name: new",
    );
  });
});

