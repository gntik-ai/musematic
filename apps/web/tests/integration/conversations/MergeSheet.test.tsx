import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { describe, expect, it, vi } from "vitest";
import { MergeSheet } from "@/components/features/conversations/MergeSheet";
import { getConversationFixtures } from "@/tests/mocks/handlers";
import { renderWithProviders } from "@/test-utils/render";
import { server } from "@/vitest.setup";

describe("MergeSheet", () => {
  it("submits selected branch messages", async () => {
    const user = userEvent.setup();
    const requestSpy = vi.fn();
    const fixtures = getConversationFixtures();

    server.use(
      http.post("*/api/v1/conversations/:conversationId/branches/:branchId/merge", async ({ request }) => {
        requestSpy(await request.json());
        return HttpResponse.json({ success: true });
      }),
    );

    renderWithProviders(
      <MergeSheet
        branch={fixtures.conversations[0]?.branches[0] ?? null}
        conversationId="conversation-1"
        messages={fixtures.branchMessages["branch-1"] ?? []}
        onOpenChange={vi.fn()}
        open
      />,
    );

    await user.click(
      screen.getByLabelText(/select message branch-message-1 for merge/i),
    );
    await user.click(
      screen.getByRole("button", { name: /merge selected messages into main thread/i }),
    );

    await waitFor(() => {
      expect(requestSpy).toHaveBeenCalledWith({
        message_ids: ["branch-message-1"],
      });
    });
  });
});
