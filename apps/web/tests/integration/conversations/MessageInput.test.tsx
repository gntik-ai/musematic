import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { describe, expect, it, vi } from "vitest";
import { MessageInput } from "@/components/features/conversations/MessageInput";
import { useConversationStore } from "@/lib/stores/conversation-store";
import { renderWithProviders } from "@/test-utils/render";
import { server } from "@/vitest.setup";

describe("MessageInput", () => {
  it("sends a mid-process injection when the agent is processing", async () => {
    const requestSpy = vi.fn();
    const user = userEvent.setup();

    useConversationStore.setState({
      ...useConversationStore.getState(),
      isAgentProcessing: true,
    });

    server.use(
      http.post("*/api/v1/interactions/:interactionId/messages", async ({ request }) => {
        requestSpy(await request.json());
        return HttpResponse.json({
          id: "message-100",
          conversation_id: "conversation-1",
          interaction_id: "interaction-1",
          sender_type: "user",
          sender_id: "user-1",
          sender_display_name: "Alex Mercer",
          content: "Guide the active agent",
          attachments: [],
          status: "complete",
          is_mid_process_injection: true,
          branch_origin: null,
          created_at: new Date().toISOString(),
          updated_at: new Date().toISOString(),
        });
      }),
    );

    renderWithProviders(
      <MessageInput
        conversationId="conversation-1"
        interactionId="interaction-1"
        isAgentProcessing
      />,
    );

    await user.type(screen.getByLabelText(/type a message/i), "Guide the active agent");
    await user.click(screen.getByRole("button", { name: /send message/i }));

    await waitFor(() => {
      expect(requestSpy).toHaveBeenCalledWith(
        expect.objectContaining({
          is_mid_process_injection: true,
        }),
      );
    });
  });
});
