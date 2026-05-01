import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { describe, expect, it, vi } from "vitest";
import {
  HypothesisFilterBar,
  type HypothesisFilterState,
} from "@/components/features/discovery/HypothesisFilterBar";
import { renderWithProviders } from "@/test-utils/render";

function FilterHarness({ onChange }: { onChange: (value: HypothesisFilterState) => void }) {
  const [value, setValue] = useState<HypothesisFilterState>({
    state: "",
    confidence: "",
    sort: "elo_desc",
  });
  return (
    <HypothesisFilterBar
      value={value}
      onChange={(nextValue) => {
        setValue(nextValue);
        onChange(nextValue);
      }}
    />
  );
}

describe("HypothesisFilterBar", () => {
  it("filters by state and confidence tier and changes sort order", async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();

    renderWithProviders(<FilterHarness onChange={onChange} />);

    await user.selectOptions(screen.getByLabelText("State"), "active");
    await user.selectOptions(screen.getByLabelText("Confidence"), "high");
    await user.selectOptions(screen.getByLabelText("Sort"), "created_at");

    expect(screen.getByLabelText("State")).toHaveValue("active");
    expect(screen.getByLabelText("Confidence")).toHaveValue("high");
    expect(screen.getByLabelText("Sort")).toHaveValue("created_at");
    expect(onChange).toHaveBeenLastCalledWith({
      state: "active",
      confidence: "high",
      sort: "created_at",
    });
  });
});
