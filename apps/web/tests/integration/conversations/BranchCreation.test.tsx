import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { describe, expect, it, vi } from "vitest";
import { BranchCreationDialog } from "@/components/features/conversations/BranchCreationDialog";
import { renderWithProviders } from "@/test-utils/render";
import { server } from "@/vitest.setup";

describe("BranchCreationDialog", () => {
  it("validates the branch name and sends the originating message id", async () => {
    const user = userEvent.setup();
    const requestSpy = vi.fn();

    server.use(
      http.post("*/api/v1/conversations/:conversationId/branches", async ({ request }) => {
        requestSpy(await request.json());
        return HttpResponse.json({
          id: "branch-2",
          conversation_id: "conversation-1",
          name: "Approach B",
          description: "Test branch",
          originating_message_id: "message-2",
          status: "active",
          created_at: new Date().toISOString(),
        });
      }),
    );

    renderWithProviders(
      <BranchCreationDialog
        conversationId="conversation-1"
        messageId="message-2"
        onOpenChange={vi.fn()}
        open
      />,
    );

    await user.click(screen.getByRole("button", { name: /create branch/i }));

    expect(await screen.findByText(/name is required/i)).toBeInTheDocument();

    await user.type(screen.getByLabelText(/^name$/i), "Approach B");
    await user.click(screen.getByRole("button", { name: /create branch/i }));

    await waitFor(() => {
      expect(requestSpy).toHaveBeenCalledWith(
        expect.objectContaining({
          originating_message_id: "message-2",
        }),
      );
    });
  });
});
