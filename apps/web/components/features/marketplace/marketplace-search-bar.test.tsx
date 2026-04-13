import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { MarketplaceSearchBar } from "@/components/features/marketplace/marketplace-search-bar";

const push = vi.fn();
let searchParams = new URLSearchParams("");

vi.mock("next/navigation", () => ({
  usePathname: () => "/marketplace",
  useRouter: () => ({ push }),
  useSearchParams: () => searchParams,
}));

describe("MarketplaceSearchBar", () => {
  beforeEach(() => {
    push.mockReset();
    searchParams = new URLSearchParams("");
  });

  it("fires onSearch after a 300ms debounce and updates the URL", async () => {
    const onSearch = vi.fn();

    render(
      <MarketplaceSearchBar
        initialValue=""
        isLoading={false}
        onSearch={onSearch}
      />,
    );

    fireEvent.change(screen.getByLabelText("Search agents"), {
      target: { value: "financial analysis" },
    });

    await waitFor(() => {
      expect(onSearch).toHaveBeenLastCalledWith("financial analysis");
      expect(push).toHaveBeenCalledWith("/marketplace?q=financial+analysis");
    }, { timeout: 1500 });
  });

  it("clears the search query", async () => {
    const user = userEvent.setup();
    const onSearch = vi.fn();

    render(
      <MarketplaceSearchBar
        initialValue="finance"
        isLoading={false}
        onSearch={onSearch}
      />,
    );

    await user.click(screen.getByLabelText("Clear search"));

    await waitFor(() => {
      expect(screen.getByLabelText("Search agents")).toHaveValue("");
      expect(onSearch).toHaveBeenLastCalledWith("");
    }, { timeout: 1500 });
  });
});
