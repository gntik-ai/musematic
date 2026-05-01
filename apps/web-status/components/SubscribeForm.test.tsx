import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { SubscribeForm } from "./SubscribeForm";

describe("SubscribeForm", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("validates email subscriptions before submitting", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch");
    const { container } = render(<SubscribeForm />);

    fireEvent.change(screen.getByLabelText("Email"), {
      target: { value: "not-an-email" },
    });
    fireEvent.submit(container.querySelector("form") as HTMLFormElement);

    expect(await screen.findByText("Check the highlighted fields and try again.")).toBeInTheDocument();
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("submits email subscriptions with anti-enumeration success text", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response("{}", {
        status: 202,
        headers: { "Content-Type": "application/json" },
      }),
    );
    const { container } = render(<SubscribeForm />);

    fireEvent.change(screen.getByLabelText("Email"), {
      target: { value: "dev@example.com" },
    });
    fireEvent.change(screen.getByLabelText("Component scope"), {
      target: { value: "control-plane-api, reasoning-engine" },
    });
    fireEvent.submit(container.querySelector("form") as HTMLFormElement);

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/v1/public/subscribe/email",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({
          email: "dev@example.com",
          scope_components: ["control-plane-api", "reasoning-engine"],
        }),
      }),
    );
    expect(
      await screen.findByText("If that address is valid, a confirmation link has been sent."),
    ).toBeInTheDocument();
  });
});
