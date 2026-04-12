import { screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { MessageContent } from "@/components/features/conversations/MessageContent";
import { MessageBubble } from "@/components/features/conversations/MessageBubble";
import { getConversationFixtures } from "@/tests/mocks/handlers";
import { renderWithProviders } from "@/test-utils/render";

describe("MessageContent", () => {
  it("renders markdown and attachments using the conversation message surface", () => {
    const fixtureMessage =
      getConversationFixtures().interactionMessages["interaction-1"][1];

    renderWithProviders(<MessageBubble message={fixtureMessage} />);

    expect(
      screen.getByRole("heading", { name: /apac summary/i }),
    ).toBeInTheDocument();
    expect(screen.getByText(/Headline/i)).toBeInTheDocument();
    expect(screen.getByText("forecast.png")).toBeInTheDocument();
    expect(screen.getByText("appendix.pdf")).toBeInTheDocument();
  });

  it("renders fenced code blocks and json content", () => {
    renderWithProviders(
      <MessageContent
        content={[
          "```python",
          "def hello():",
          '    return "world"',
          "```",
          "",
          "```json",
          '{ "hello": "world" }',
          "```",
        ].join("\n")}
      />,
    );

    expect(screen.getByRole("button", { name: /copy code block/i })).toBeInTheDocument();
    expect(screen.getByText(/root/i)).toBeInTheDocument();
  });
});
