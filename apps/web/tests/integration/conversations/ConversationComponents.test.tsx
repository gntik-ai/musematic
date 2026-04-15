import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { AttachmentCard } from "@/components/features/conversations/AttachmentCard";
import { BranchOriginIndicator } from "@/components/features/conversations/BranchOriginIndicator";
import { CodeBlock } from "@/components/features/conversations/CodeBlock";
import { MergedFromBadge } from "@/components/features/conversations/MergedFromBadge";
import { MessageBubble } from "@/components/features/conversations/MessageBubble";
import { MidProcessBadge } from "@/components/features/conversations/MidProcessBadge";
import { NewMessagesPill } from "@/components/features/conversations/NewMessagesPill";
import { StatusBar } from "@/components/features/conversations/StatusBar";
import { renderWithProviders } from "@/test-utils/render";
import { getConversationFixtures } from "@/tests/mocks/handlers";

describe("conversation components", () => {
  it("renders status states and badges", () => {
    const fixtures = getConversationFixtures();
    const activeInteraction = fixtures.conversations[0]?.interactions[0];
    const approvalInteraction = fixtures.conversations[0]?.interactions[1];
    const completedInteraction = fixtures.conversations[1]?.interactions[0];

    if (!activeInteraction || !approvalInteraction || !completedInteraction) {
      throw new Error("Expected interaction fixtures");
    }

    const { rerender } = renderWithProviders(
      <StatusBar interaction={activeInteraction} isProcessing />,
    );

    expect(screen.getByText("finance-ops:analyzer")).toBeInTheDocument();
    expect(screen.getByText("Chain of Thought")).toBeInTheDocument();
    expect(screen.getByText("3 corrections")).toBeInTheDocument();
    expect(screen.getByText("Processing")).toBeInTheDocument();

    rerender(
      <StatusBar interaction={approvalInteraction} isProcessing={false} />,
    );
    expect(screen.getByText("Awaiting Approval")).toBeInTheDocument();
    expect(screen.getByText("Tree of Thought")).toBeInTheDocument();

    rerender(
      <StatusBar interaction={completedInteraction} isProcessing={false} />,
    );
    expect(screen.getByText("Completed")).toBeInTheDocument();
    expect(screen.getByText("—")).toBeInTheDocument();
  });

  it("renders message bubble affordances for attachments, branches, and truncation", async () => {
    const user = userEvent.setup();
    const fixtures = getConversationFixtures();
    const message = fixtures.interactionMessages["interaction-1"]?.[1];

    if (!message) {
      throw new Error("Expected message fixture");
    }

    renderWithProviders(
      <MessageBubble
        message={{
          ...message,
          branch_origin: "Approach B",
          content: `${"A".repeat(50_001)}\nconsole.log('ok')`,
          is_mid_process_injection: true,
        }}
        onBranchFrom={() => {}}
        showBranchOriginIndicator
      />,
    );

    expect(screen.getByLabelText("Has branches")).toBeInTheDocument();
    expect(screen.getByText("sent during processing")).toBeInTheDocument();
    expect(screen.getByText("from: Approach B")).toBeInTheDocument();
    expect(screen.getByText(/show more/i)).toBeInTheDocument();

    await user.click(screen.getByText(/show more/i));
    expect(screen.getByText(/show less/i)).toBeInTheDocument();

    await user.click(screen.getByLabelText("Message actions"));
    expect(screen.getByRole("button", { name: "Branch from this message" })).toBeInTheDocument();
    expect(screen.getByText("forecast.png")).toBeInTheDocument();
    expect(screen.getByText("appendix.pdf")).toBeInTheDocument();
  });

  it("renders image and file attachments, code blocks, and the new message pill", async () => {
    const user = userEvent.setup();

    renderWithProviders(
      <div>
        <AttachmentCard
          attachment={{
            id: "attachment-image",
            filename: "diagram.png",
            mime_type: "image/png",
            size_bytes: 2048,
            url: "https://example.com/diagram.png",
          }}
        />
        <AttachmentCard
          attachment={{
            id: "attachment-json",
            filename: "payload.json",
            mime_type: "application/json",
            size_bytes: 512,
            url: "https://example.com/payload.json",
          }}
        />
        <AttachmentCard
          attachment={{
            id: "attachment-text",
            filename: "notes.pdf",
            mime_type: "application/pdf",
            size_bytes: 1500,
            url: "https://example.com/notes.pdf",
          }}
        />
        <CodeBlock
          code={Array.from({ length: 45 }, (_, index) => `line ${index + 1}`).join("\n")}
          language="json"
        />
        <NewMessagesPill count={0} onClick={() => {}} />
        <NewMessagesPill count={1} onClick={() => {}} />
        <BranchOriginIndicator />
        <MergedFromBadge branchName="Fallback path" />
        <MidProcessBadge />
      </div>,
    );

    expect(screen.getByRole("img", { name: "diagram.png" })).toBeInTheDocument();
    await user.click(screen.getByRole("img", { name: "diagram.png" }));
    expect(screen.getAllByRole("img", { name: "diagram.png" })).toHaveLength(2);

    expect(screen.getByRole("link", { name: /payload.json/i })).toHaveAttribute(
      "href",
      "https://example.com/payload.json",
    );
    expect(screen.getByRole("link", { name: /notes.pdf/i })).toHaveAttribute(
      "href",
      "https://example.com/notes.pdf",
    );

    await user.click(screen.getByRole("button", { name: /show all 45 lines/i }));
    expect(screen.getByRole("button", { name: /show less/i })).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /copy code block/i }));
    expect(screen.getByRole("button", { name: /copy code block/i })).toHaveTextContent(
      "Copied!",
    );

    expect(screen.queryByLabelText(/0 new messages/i)).not.toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: /1 new messages, scroll to bottom/i }),
    ).toHaveTextContent("1 new message");
  });

  it("renders a centered system message", () => {
    render(
      <MessageBubble
        message={{
          id: "system-1",
          conversation_id: "conversation-1",
          interaction_id: "interaction-1",
          sender_type: "system",
          sender_id: "system",
          sender_display_name: "System",
          content: "Approval requested.",
          attachments: [],
          status: "complete",
          is_mid_process_injection: false,
          branch_origin: null,
          created_at: "2026-04-12T10:00:00.000Z",
          updated_at: "2026-04-12T10:00:00.000Z",
        }}
      />,
    );

    expect(screen.getByLabelText("System message")).toBeInTheDocument();
    expect(screen.getByText("Approval requested.")).toBeInTheDocument();
  });

  it("renders user messages with custom children, branch indicators, and streaming affordances", () => {
    render(
      <MessageBubble
        isStreaming
        message={{
          id: "user-1",
          conversation_id: "conversation-1",
          interaction_id: "interaction-1",
          sender_type: "user",
          sender_id: "user-1",
          sender_display_name: "",
          content: "Original user content",
          attachments: [],
          status: "streaming",
          is_mid_process_injection: false,
          branch_origin: null,
          created_at: "2026-04-12T10:00:00.000Z",
          updated_at: "2026-04-12T10:00:00.000Z",
        }}
        showBranchOriginIndicator
      >
        <span>Injected child content</span>
      </MessageBubble>,
    );

    expect(screen.getByLabelText("User message")).toBeInTheDocument();
    expect(screen.getByLabelText("Has branches")).toBeInTheDocument();
    expect(screen.getByText("Injected child content")).toBeInTheDocument();
  });
});
