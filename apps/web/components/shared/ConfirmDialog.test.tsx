import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { ConfirmDialog } from "@/components/shared/ConfirmDialog";

describe("ConfirmDialog", () => {
  it("calls onConfirm when the confirm action is clicked", () => {
    const onConfirm = vi.fn();
    render(
      <ConfirmDialog
        description="Delete the item"
        onConfirm={onConfirm}
        onOpenChange={vi.fn()}
        open
        title="Delete item"
      />,
    );

    fireEvent.click(screen.getByText("Confirm"));
    expect(onConfirm).toHaveBeenCalledTimes(1);
  });

  it("disables actions in loading state", () => {
    render(
      <ConfirmDialog
        description="Delete the item"
        isLoading
        onConfirm={vi.fn()}
        onOpenChange={vi.fn()}
        open
        title="Delete item"
      />,
    );

    expect(screen.getByText("Confirm")).toBeDisabled();
  });
});
