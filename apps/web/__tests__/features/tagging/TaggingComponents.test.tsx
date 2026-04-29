import { fireEvent, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { CrossEntityTagSearch } from "@/components/features/tagging/CrossEntityTagSearch";
import { LabelEditor } from "@/components/features/tagging/LabelEditor";
import { LabelExpressionEditor } from "@/components/features/tagging/LabelExpressionEditor";
import { SavedViewPicker } from "@/components/features/tagging/SavedViewPicker";
import { TagEditor } from "@/components/features/tagging/TagEditor";
import { renderWithProviders } from "@/test-utils/render";

const apiMocks = vi.hoisted(() => ({
  useCrossEntityTagSearch: vi.fn(),
  useEntityLabels: vi.fn(),
  useEntityTags: vi.fn(),
  useLabelDetach: vi.fn(),
  useLabelExpressionValidate: vi.fn(),
  useLabelUpsert: vi.fn(),
  useSavedViewShare: vi.fn(),
  useSavedViews: vi.fn(),
  useTagAttach: vi.fn(),
  useTagDetach: vi.fn(),
}));

vi.mock("@/lib/api/tagging", () => apiMocks);

vi.mock("@monaco-editor/react", () => ({
  default: ({
    value,
    onChange,
  }: {
    value: string;
    onChange: (value: string | undefined) => void;
  }) => (
    <textarea
      aria-label="Label expression"
      onChange={(event) => onChange(event.currentTarget.value)}
      value={value}
    />
  ),
}));

function tag(value: string) {
  return {
    created_at: "2026-04-29T08:00:00.000Z",
    created_by: "user-1",
    tag: value,
  };
}

function label(key: string, value: string, isReserved = false) {
  return {
    created_at: "2026-04-29T08:00:00.000Z",
    created_by: "user-1",
    is_reserved: isReserved,
    key,
    updated_at: "2026-04-29T08:00:00.000Z",
    value,
  };
}

function savedView(overrides: Record<string, unknown>) {
  return {
    created_at: "2026-04-29T08:00:00.000Z",
    entity_type: "agent",
    filters: { "label.env": "production" },
    id: "view-1",
    is_orphan: false,
    is_orphan_transferred: false,
    is_owner: true,
    is_shared: false,
    name: "Production agents",
    owner_id: "user-1",
    updated_at: "2026-04-29T08:00:00.000Z",
    version: 1,
    workspace_id: "workspace-1",
    ...overrides,
  };
}

describe("tagging components", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    apiMocks.useEntityTags.mockReturnValue({ data: { tags: [] } });
    apiMocks.useTagAttach.mockReturnValue({ mutateAsync: vi.fn().mockResolvedValue(undefined) });
    apiMocks.useTagDetach.mockReturnValue({ mutate: vi.fn() });
    apiMocks.useEntityLabels.mockReturnValue({ data: { labels: [] } });
    apiMocks.useLabelUpsert.mockReturnValue({ mutateAsync: vi.fn().mockResolvedValue(undefined) });
    apiMocks.useLabelDetach.mockReturnValue({ mutate: vi.fn() });
    apiMocks.useSavedViews.mockReturnValue({ data: [] });
    apiMocks.useSavedViewShare.mockReturnValue({ mutate: vi.fn() });
    apiMocks.useLabelExpressionValidate.mockReturnValue({ data: null });
    apiMocks.useCrossEntityTagSearch.mockReturnValue({ data: { entities: {} } });
  });

  it("shows the tag ceiling before allowing another attach", () => {
    apiMocks.useEntityTags.mockReturnValue({
      data: { tags: Array.from({ length: 50 }, (_, index) => tag(`tag-${index}`)) },
    });

    renderWithProviders(<TagEditor entityId="agent-1" entityType="agent" />);

    expect(screen.getByLabelText("Tag")).toBeDisabled();
    expect(screen.getByText("50 tag limit reached")).toBeInTheDocument();
    expect(screen.getByLabelText("Add tag")).toBeDisabled();
  });

  it("rejects invalid and duplicate tags before mutation", async () => {
    const user = userEvent.setup();
    const attach = vi.fn().mockResolvedValue(undefined);
    apiMocks.useEntityTags.mockReturnValue({ data: { tags: [tag("production")] } });
    apiMocks.useTagAttach.mockReturnValue({ mutateAsync: attach });

    renderWithProviders(<TagEditor entityId="agent-1" entityType="agent" />);

    await user.type(screen.getByLabelText("Tag"), "bad tag");
    expect(screen.getByText(/Tags use letters/)).toBeInTheDocument();
    expect(screen.getByLabelText("Add tag")).toBeDisabled();

    await user.clear(screen.getByLabelText("Tag"));
    await user.type(screen.getByLabelText("Tag"), "production");
    expect(screen.getByText("Tag already applied")).toBeInTheDocument();
    expect(screen.getByLabelText("Add tag")).toBeDisabled();
    expect(attach).not.toHaveBeenCalled();
  });

  it("locks reserved label rows and prevents non-superadmin reserved writes", async () => {
    const user = userEvent.setup();
    apiMocks.useEntityLabels.mockReturnValue({
      data: { labels: [label("system.managed", "true", true)] },
    });

    renderWithProviders(
      <LabelEditor canEditReserved={false} entityId="agent-1" entityType="agent" />,
    );

    expect(screen.getByText("Reserved")).toBeInTheDocument();
    expect(screen.getByText("Editable by superadmins and service accounts only.")).toBeInTheDocument();
    expect(screen.queryByLabelText("Remove system.managed")).not.toBeInTheDocument();

    await user.type(screen.getByLabelText("Label key"), "system.managed");
    await user.type(screen.getByLabelText("Label value"), "false");

    expect(screen.getByText(/Reserved label keys require/)).toBeInTheDocument();
    expect(screen.getByLabelText("Add label")).toBeDisabled();
  });

  it("allows superadmins to upsert reserved labels", async () => {
    const user = userEvent.setup();
    const upsert = vi.fn().mockResolvedValue(undefined);
    apiMocks.useLabelUpsert.mockReturnValue({ mutateAsync: upsert });

    renderWithProviders(
      <LabelEditor canEditReserved entityId="agent-1" entityType="agent" />,
    );

    await user.type(screen.getByLabelText("Label key"), "system.managed");
    await user.type(screen.getByLabelText("Label value"), "true");
    await user.click(screen.getByLabelText("Add label"));

    expect(upsert).toHaveBeenCalledWith({ key: "system.managed", value: "true" });
  });

  it("applies saved views and exposes owner share toggles", () => {
    const onApply = vi.fn();
    const share = vi.fn();
    apiMocks.useSavedViews.mockReturnValue({
      data: [
        savedView({ id: "personal-view" }),
        savedView({
          id: "shared-view",
          is_orphan_transferred: true,
          is_owner: false,
          is_shared: true,
          name: "Shared production",
        }),
      ],
    });
    apiMocks.useSavedViewShare.mockReturnValue({ mutate: share });

    renderWithProviders(
      <SavedViewPicker entityType="agent" onApply={onApply} workspaceId="workspace-1" />,
    );

    fireEvent.change(screen.getByLabelText("Saved view"), { target: { value: "shared-view" } });
    expect(onApply).toHaveBeenCalledWith(expect.objectContaining({ id: "shared-view" }));
    expect(screen.getByRole("option", { name: /shared/i })).toHaveTextContent("former member");

    fireEvent.click(screen.getByLabelText("Toggle share"));
    expect(share).toHaveBeenCalledWith({ id: "personal-view", shared: true });
  });

  it("renders label expression validation states from the debounced value", () => {
    const onChange = vi.fn();
    apiMocks.useLabelExpressionValidate.mockReturnValue({
      data: {
        error: {
          col: 20,
          line: 1,
          message: "Expected comparison",
          token: "<EOF>",
        },
        valid: false,
      },
    });

    renderWithProviders(<LabelExpressionEditor onChange={onChange} value="env=production AND" />);

    expect(screen.getByText("1:20 Expected comparison")).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Label expression"), {
      target: { value: "env=production" },
    });
    expect(onChange).toHaveBeenCalledWith("env=production");
  });

  it("groups cross-entity tag results with click-through detail links", async () => {
    const user = userEvent.setup();
    apiMocks.useCrossEntityTagSearch.mockReturnValue({
      data: {
        entities: {
          agent: ["risk:kyc-monitor"],
          policy: ["policy-1"],
        },
      },
    });

    renderWithProviders(<CrossEntityTagSearch />);

    await user.type(screen.getByLabelText("Cross-entity tag search"), "tag:production");

    expect(apiMocks.useCrossEntityTagSearch).toHaveBeenLastCalledWith("production");
    expect(screen.getByText("agent")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "risk:kyc-monitor" })).toHaveAttribute(
      "href",
      "/agent-management/risk%3Akyc-monitor",
    );
    expect(screen.getByRole("link", { name: "policy-1" })).toHaveAttribute(
      "href",
      "/policies?policy_id=policy-1",
    );
  });
});
