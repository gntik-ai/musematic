import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { JsonViewer } from "@/components/shared/JsonViewer";

describe("JsonViewer", () => {
  it("renders nested keys", () => {
    render(<JsonViewer value={{ root: { leaf: true } }} />);
    expect(screen.getAllByText("root")).toHaveLength(2);
  });

  it("copies JSON to the clipboard", () => {
    const writeText = vi.spyOn(navigator.clipboard, "writeText");
    render(<JsonViewer value={{ root: { leaf: true } }} />);
    fireEvent.click(screen.getByText("Copy"));
    expect(writeText).toHaveBeenCalled();
  });
});
