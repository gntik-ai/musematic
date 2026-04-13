import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { RecoveryCodesStep } from "@/components/features/auth/mfa-enrollment/RecoveryCodesStep";

describe("RecoveryCodesStep", () => {
  it("keeps completion disabled until the acknowledgement is checked", async () => {
    const user = userEvent.setup();
    const onComplete = vi.fn();

    render(
      <RecoveryCodesStep
        onComplete={onComplete}
        recoveryCodes={["alpha", "bravo"]}
      />,
    );

    const completeButton = screen.getByRole("button", { name: /complete setup/i });
    expect(completeButton).toBeDisabled();

    await user.click(
      screen.getByLabelText(/i have saved my recovery codes in a safe place/i),
    );

    expect(completeButton).toBeEnabled();
    await user.click(completeButton);

    expect(onComplete).toHaveBeenCalledTimes(1);
  });

  it("copies every recovery code to the clipboard", async () => {
    const user = userEvent.setup();
    const writeText = vi
      .spyOn(navigator.clipboard, "writeText")
      .mockResolvedValue(undefined);

    render(
      <RecoveryCodesStep
        onComplete={vi.fn()}
        recoveryCodes={["alpha", "bravo", "charlie"]}
      />,
    );

    await user.click(screen.getByRole("button", { name: /copy all codes/i }));

    expect(writeText).toHaveBeenCalledWith(
      "alpha\nbravo\ncharlie",
    );
    expect(screen.getByRole("button", { name: /copied!/i })).toBeInTheDocument();
  });
});
