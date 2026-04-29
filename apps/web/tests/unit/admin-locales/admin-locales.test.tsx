import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { DriftStatusBadge, LocaleFilePublishForm } from "@/components/features/admin-locales";
import { usePublishLocaleFile } from "@/lib/api/locales";

const mutateAsync = vi.fn();

vi.mock("@/lib/api/locales", () => ({
  usePublishLocaleFile: vi.fn(),
}));

describe("admin locale components", () => {
  beforeEach(() => {
    mutateAsync.mockReset();
    mutateAsync.mockResolvedValue({});
    vi.mocked(usePublishLocaleFile).mockReturnValue({
      mutateAsync,
      isPending: false,
    } as never);
  });

  it("previews namespace and key counts before publishing", async () => {
    render(<LocaleFilePublishForm />);

    fireEvent.change(screen.getByLabelText("Translations JSON"), {
      target: { value: JSON.stringify({ common: { save: "Save" } }) },
    });

    expect(screen.getByTestId("locale-json-preview")).toHaveTextContent("1 namespaces, 1 keys");
    fireEvent.click(screen.getByRole("button", { name: /publish locale file/i }));

    await waitFor(() => {
      expect(mutateAsync).toHaveBeenCalledWith(
        expect.objectContaining({
          locale_code: "en",
          translations: { common: { save: "Save" } },
        }),
      );
    });
  });

  it("renders drift severity states", () => {
    render(<DriftStatusBadge status="over_threshold" />);
    expect(screen.getByText("Over threshold")).toBeInTheDocument();
  });
});
