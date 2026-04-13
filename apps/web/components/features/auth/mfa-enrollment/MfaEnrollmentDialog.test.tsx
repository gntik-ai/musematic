import { fireEvent, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { MfaEnrollmentDialog } from "@/components/features/auth/mfa-enrollment/MfaEnrollmentDialog";
import { renderWithProviders } from "@/test-utils/render";

async function advanceToRecoveryCodes() {
  const user = userEvent.setup();

  await screen.findByRole("button", { name: /next/i });
  await user.click(screen.getByRole("button", { name: /next/i }));
  await user.type(
    screen.getByLabelText(/authenticator verification code/i),
    "123456",
  );

  await waitFor(() => {
    expect(
      screen.getByText(/save your recovery codes/i),
    ).toBeInTheDocument();
  });

  return user;
}

describe("MfaEnrollmentDialog", () => {
  it("renders when open is true", async () => {
    renderWithProviders(
      <MfaEnrollmentDialog onEnrolled={vi.fn()} open />,
    );

    expect(await screen.findByText(/set up authenticator/i)).toBeInTheDocument();
    expect(screen.getByRole("dialog")).toBeInTheDocument();
  });

  it("moves from the QR step to verification and then recovery codes", async () => {
    const user = userEvent.setup();

    renderWithProviders(
      <MfaEnrollmentDialog onEnrolled={vi.fn()} open />,
    );

    await screen.findByRole("button", { name: /next/i });
    await user.click(screen.getByRole("button", { name: /next/i }));
    expect(screen.getByText(/confirm your authenticator/i)).toBeInTheDocument();

    await user.type(
      screen.getByLabelText(/authenticator verification code/i),
      "123456",
    );

    await waitFor(() => {
      expect(
        screen.getByText(/save your recovery codes/i),
      ).toBeInTheDocument();
    });
  });

  it("blocks escape and outside clicks while recovery codes are visible", async () => {
    renderWithProviders(
      <MfaEnrollmentDialog onEnrolled={vi.fn()} open />,
    );

    await advanceToRecoveryCodes();

    fireEvent.keyDown(window, { key: "Escape" });
    expect(screen.getByText(/save your recovery codes/i)).toBeInTheDocument();

    const overlay = screen.getByRole("dialog").parentElement as HTMLElement;
    fireEvent.mouseDown(overlay);

    expect(screen.getByText(/save your recovery codes/i)).toBeInTheDocument();
  });

  it("calls onEnrolled after the recovery codes are acknowledged", async () => {
    const onEnrolled = vi.fn();
    const user = userEvent.setup();

    renderWithProviders(
      <MfaEnrollmentDialog onEnrolled={onEnrolled} open />,
    );

    await advanceToRecoveryCodes();

    await user.click(
      screen.getByLabelText(/i have saved my recovery codes in a safe place/i),
    );
    await user.click(screen.getByRole("button", { name: /complete setup/i }));

    expect(onEnrolled).toHaveBeenCalledTimes(1);
  });
});
