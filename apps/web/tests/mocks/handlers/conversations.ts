import { http, HttpResponse } from "msw";
import type {
  BranchCreateRequest,
  BranchMergeRequest,
  Conversation,
  ConversationBranch,
  GoalMessage,
  GoalMessageRequest,
  Message,
  PaginatedMessageResponse,
  SendMessageRequest,
  WorkspaceGoal,
} from "@/types/conversations";

type ConversationFixtures = {
  conversations: Conversation[];
  interactionMessages: Record<string, Message[]>;
  branchMessages: Record<string, Message[]>;
  workspaceGoals: Record<string, WorkspaceGoal[]>;
  goalMessages: Record<string, GoalMessage[]>;
};

function createConversationFixtures(): ConversationFixtures {
  const now = new Date("2026-04-12T10:00:00.000Z");
  const iso = (offsetMinutes: number) =>
    new Date(now.getTime() + offsetMinutes * 60_000).toISOString();

  const conversations: Conversation[] = [
    {
      id: "conversation-1",
      workspace_id: "workspace-1",
      title: "Quarterly performance review",
      created_at: iso(-80),
      interactions: [
        {
          id: "interaction-1",
          conversation_id: "conversation-1",
          agent_id: "agent-1",
          agent_fqn: "finance-ops:analyzer",
          agent_display_name: "Finance Analyzer",
          state: "active",
          reasoning_mode: "chain_of_thought",
          self_correction_count: 3,
          created_at: iso(-80),
          updated_at: iso(-5),
        },
        {
          id: "interaction-2",
          conversation_id: "conversation-1",
          agent_id: "agent-2",
          agent_fqn: "trust:reviewer",
          agent_display_name: "Trust Reviewer",
          state: "awaiting_approval",
          reasoning_mode: "tree_of_thought",
          self_correction_count: 1,
          created_at: iso(-60),
          updated_at: iso(-8),
        },
      ],
      branches: [
        {
          id: "branch-1",
          conversation_id: "conversation-1",
          name: "Approach B",
          description: "Explore a cost-focused angle",
          originating_message_id: "message-2",
          status: "active",
          created_at: iso(-20),
        },
      ],
    },
    {
      id: "conversation-2",
      workspace_id: "workspace-1",
      title: "Launch readiness audit",
      created_at: iso(-180),
      interactions: [
        {
          id: "interaction-3",
          conversation_id: "conversation-2",
          agent_id: "agent-3",
          agent_fqn: "ops:planner",
          agent_display_name: "Ops Planner",
          state: "completed",
          reasoning_mode: "none",
          self_correction_count: 0,
          created_at: iso(-180),
          updated_at: iso(-120),
        },
      ],
      branches: [],
    },
  ];

  const interactionMessages: Record<string, Message[]> = {
    "interaction-1": [
      {
        id: "message-1",
        conversation_id: "conversation-1",
        interaction_id: "interaction-1",
        sender_type: "user",
        sender_id: "user-1",
        sender_display_name: "Alex Mercer",
        content: "Summarize the quarter and focus on APAC risk.",
        attachments: [],
        status: "complete",
        is_mid_process_injection: false,
        branch_origin: null,
        created_at: iso(-78),
        updated_at: iso(-78),
      },
      {
        id: "message-2",
        conversation_id: "conversation-1",
        interaction_id: "interaction-1",
        sender_type: "agent",
        sender_id: "finance-ops:analyzer",
        sender_display_name: "Finance Analyzer",
        content: [
          "# APAC summary",
          "",
          "**Headline**: revenue was resilient despite margin compression.",
          "",
          "- APAC revenue grew 12%",
          "- Margin dipped 2 points",
          "",
          "| Metric | Value |",
          "| --- | --- |",
          "| Revenue | $4.2M |",
          "| Margin | 18% |",
          "",
          "```json",
          '{ "region": "APAC", "risk": "medium", "trend": ["growth", "margin pressure"] }',
          "```",
        ].join("\n"),
        attachments: [
          {
            id: "attachment-1",
            filename: "forecast.png",
            mime_type: "image/png",
            size_bytes: 210432,
            url: "https://example.com/files/forecast.png",
          },
          {
            id: "attachment-2",
            filename: "appendix.pdf",
            mime_type: "application/pdf",
            size_bytes: 814321,
            url: "https://example.com/files/appendix.pdf",
          },
        ],
        status: "complete",
        is_mid_process_injection: false,
        branch_origin: null,
        created_at: iso(-76),
        updated_at: iso(-76),
      },
      {
        id: "message-3",
        conversation_id: "conversation-1",
        interaction_id: "interaction-1",
        sender_type: "system",
        sender_id: "system",
        sender_display_name: "System",
        content: "Awaiting approval from trust reviewer.",
        attachments: [],
        status: "complete",
        is_mid_process_injection: false,
        branch_origin: null,
        created_at: iso(-74),
        updated_at: iso(-74),
      },
    ],
    "interaction-2": [
      {
        id: "message-4",
        conversation_id: "conversation-1",
        interaction_id: "interaction-2",
        sender_type: "agent",
        sender_id: "trust:reviewer",
        sender_display_name: "Trust Reviewer",
        content: "I need more detail on the regional compliance posture.",
        attachments: [],
        status: "complete",
        is_mid_process_injection: false,
        branch_origin: null,
        created_at: iso(-58),
        updated_at: iso(-58),
      },
      {
        id: "message-5",
        conversation_id: "conversation-1",
        interaction_id: "interaction-2",
        sender_type: "user",
        sender_id: "user-1",
        sender_display_name: "Alex Mercer",
        content: "Use the APAC compliance appendix as source of truth.",
        attachments: [],
        status: "complete",
        is_mid_process_injection: false,
        branch_origin: null,
        created_at: iso(-56),
        updated_at: iso(-56),
      },
    ],
    "interaction-3": [
      {
        id: "message-6",
        conversation_id: "conversation-2",
        interaction_id: "interaction-3",
        sender_type: "agent",
        sender_id: "ops:planner",
        sender_display_name: "Ops Planner",
        content: "Launch readiness audit completed.",
        attachments: [],
        status: "complete",
        is_mid_process_injection: false,
        branch_origin: null,
        created_at: iso(-170),
        updated_at: iso(-170),
      },
    ],
  };

  const branchMessages: Record<string, Message[]> = {
    "branch-1": [
      {
        id: "branch-message-1",
        conversation_id: "conversation-1",
        interaction_id: "interaction-1",
        sender_type: "agent",
        sender_id: "finance-ops:analyzer",
        sender_display_name: "Finance Analyzer",
        content: "Alternative path: reduce vendor spend by 8%.",
        attachments: [],
        status: "complete",
        is_mid_process_injection: false,
        branch_origin: null,
        created_at: iso(-18),
        updated_at: iso(-18),
      },
      {
        id: "branch-message-2",
        conversation_id: "conversation-1",
        interaction_id: "interaction-1",
        sender_type: "agent",
        sender_id: "finance-ops:analyzer",
        sender_display_name: "Finance Analyzer",
        content: "Alternative path: stage APAC hiring across two quarters.",
        attachments: [],
        status: "complete",
        is_mid_process_injection: false,
        branch_origin: null,
        created_at: iso(-17),
        updated_at: iso(-17),
      },
    ],
  };

  const workspaceGoals: Record<string, WorkspaceGoal[]> = {
    "workspace-1": [
      {
        id: "goal-1",
        workspace_id: "workspace-1",
        title: "Q2 Sales Analysis",
        description: "Align the regional storyline for executive review.",
        status: "active",
        created_at: iso(-120),
      },
      {
        id: "goal-2",
        workspace_id: "workspace-1",
        title: "Trust Escalation Queue",
        description: "Review open issues that need a human decision.",
        status: "paused",
        created_at: iso(-90),
      },
    ],
  };

  const goalMessages: Record<string, GoalMessage[]> = {
    "goal-1": [
      {
        id: "goal-message-1",
        goal_id: "goal-1",
        sender_type: "agent",
        sender_id: "finance-ops:analyzer",
        sender_display_name: "Finance Analyzer",
        agent_fqn: "finance-ops:analyzer",
        content: "APAC remains the region with the strongest revenue acceleration.",
        originating_interaction_id: "interaction-1",
        created_at: iso(-30),
      },
      {
        id: "goal-message-2",
        goal_id: "goal-1",
        sender_type: "user",
        sender_id: "user-1",
        sender_display_name: "Alex Mercer",
        agent_fqn: null,
        content: "Keep the narrative tied to the board review memo.",
        originating_interaction_id: null,
        created_at: iso(-26),
      },
    ],
    "goal-2": [
      {
        id: "goal-message-3",
        goal_id: "goal-2",
        sender_type: "system",
        sender_id: "system",
        sender_display_name: "System",
        agent_fqn: null,
        content: "Trust queue paused until the next review window.",
        originating_interaction_id: null,
        created_at: iso(-24),
      },
    ],
  };

  return {
    conversations,
    interactionMessages,
    branchMessages,
    workspaceGoals,
    goalMessages,
  };
}

let fixtures = createConversationFixtures();

export function resetConversationFixtures() {
  fixtures = createConversationFixtures();
}

export function getConversationFixtures() {
  return fixtures;
}

function findConversation(conversationId: string): Conversation | undefined {
  return fixtures.conversations.find((conversation) => conversation.id === conversationId);
}

function findBranch(conversationId: string, branchId: string): ConversationBranch | undefined {
  return findConversation(conversationId)?.branches.find((branch) => branch.id === branchId);
}

function paginate<T>(items: T[], cursor: string | null, limit: number): PaginatedMessageResponse<T> {
  const offset = cursor ? Number.parseInt(cursor, 10) : 0;
  const safeOffset = Number.isFinite(offset) ? offset : 0;
  const nextItems = items.slice(safeOffset, safeOffset + limit);
  const nextCursor =
    safeOffset + limit < items.length ? String(safeOffset + limit) : null;

  return {
    items: nextItems,
    next_cursor: nextCursor,
  };
}

function createMessageId(prefix: string) {
  return `${prefix}-${Math.random().toString(16).slice(2, 10)}`;
}

function createIsoNow() {
  return new Date().toISOString();
}

export const conversationHandlers = [
  http.get("*/api/v1/conversations", ({ request }) => {
    const workspaceId = new URL(request.url).searchParams.get("workspace_id");
    const items = workspaceId
      ? fixtures.conversations.filter(
          (conversation) => conversation.workspace_id === workspaceId,
        )
      : fixtures.conversations;

    return HttpResponse.json({ items });
  }),
  http.get("*/api/v1/conversations/:conversationId", ({ params }) => {
    const conversation = findConversation(String(params.conversationId));

    if (!conversation) {
      return HttpResponse.json(
        { error: { code: "not_found", message: "Conversation not found" } },
        { status: 404 },
      );
    }

    return HttpResponse.json(conversation);
  }),
  http.get("*/api/v1/interactions/:interactionId/messages", ({ params, request }) => {
    const interactionId = String(params.interactionId);
    const searchParams = new URL(request.url).searchParams;
    const cursor = searchParams.get("cursor");
    const limit = Number.parseInt(searchParams.get("limit") ?? "50", 10);
    const items = fixtures.interactionMessages[interactionId] ?? [];

    return HttpResponse.json(paginate(items, cursor, limit));
  }),
  http.post("*/api/v1/interactions/:interactionId/messages", async ({ params, request }) => {
    const interactionId = String(params.interactionId);
    const body = (await request.json()) as SendMessageRequest;
    const interaction = fixtures.conversations
      .flatMap((conversation) => conversation.interactions)
      .find((item) => item.id === interactionId);

    if (!interaction) {
      return HttpResponse.json(
        { error: { code: "not_found", message: "Interaction not found" } },
        { status: 404 },
      );
    }

    const now = createIsoNow();
    const message: Message = {
      id: createMessageId("message"),
      conversation_id: interaction.conversation_id,
      interaction_id: interactionId,
      sender_type: "user",
      sender_id: "user-1",
      sender_display_name: "Alex Mercer",
      content: body.content,
      attachments: [],
      status: "complete",
      is_mid_process_injection: body.is_mid_process_injection,
      branch_origin: null,
      created_at: now,
      updated_at: now,
    };

    fixtures.interactionMessages[interactionId] = [
      ...(fixtures.interactionMessages[interactionId] ?? []),
      message,
    ];

    return HttpResponse.json(message, { status: 201 });
  }),
  http.get(
    "*/api/v1/conversations/:conversationId/branches/:branchId/messages",
    ({ params, request }) => {
      const branchId = String(params.branchId);
      const searchParams = new URL(request.url).searchParams;
      const cursor = searchParams.get("cursor");
      const limit = Number.parseInt(searchParams.get("limit") ?? "50", 10);
      const items = fixtures.branchMessages[branchId] ?? [];

      return HttpResponse.json(paginate(items, cursor, limit));
    },
  ),
  http.post("*/api/v1/conversations/:conversationId/branches", async ({ params, request }) => {
    const conversationId = String(params.conversationId);
    const body = (await request.json()) as BranchCreateRequest;
    const conversation = findConversation(conversationId);

    if (!conversation) {
      return HttpResponse.json(
        { error: { code: "not_found", message: "Conversation not found" } },
        { status: 404 },
      );
    }

    const branch: ConversationBranch = {
      id: createMessageId("branch"),
      conversation_id: conversationId,
      name: body.name,
      description: body.description ?? null,
      originating_message_id: body.originating_message_id,
      status: "active",
      created_at: createIsoNow(),
    };

    conversation.branches = [...conversation.branches, branch];
    fixtures.branchMessages[branch.id] = [];

    return HttpResponse.json(branch, { status: 201 });
  }),
  http.post(
    "*/api/v1/conversations/:conversationId/branches/:branchId/merge",
    async ({ params, request }) => {
      const conversationId = String(params.conversationId);
      const branchId = String(params.branchId);
      const body = (await request.json()) as BranchMergeRequest;
      const conversation = findConversation(conversationId);
      const branch = findBranch(conversationId, branchId);

      if (!conversation || !branch) {
        return HttpResponse.json(
          { error: { code: "not_found", message: "Branch not found" } },
          { status: 404 },
        );
      }

      const sourceMessages = fixtures.branchMessages[branchId] ?? [];
      const selectedMessages = sourceMessages.filter((message) =>
        body.message_ids.includes(message.id),
      );
      const targetInteractionId =
        selectedMessages[0]?.interaction_id ??
        conversation.interactions[0]?.id ??
        null;

      if (targetInteractionId) {
        const mergedMessages = selectedMessages.map((message) => ({
          ...message,
          id: createMessageId("merged-message"),
          branch_origin: branch.name,
          created_at: createIsoNow(),
          updated_at: createIsoNow(),
        }));

        fixtures.interactionMessages[targetInteractionId] = [
          ...(fixtures.interactionMessages[targetInteractionId] ?? []),
          ...mergedMessages,
        ];
      }

      branch.status = "merged";

      return HttpResponse.json({
        success: true,
        merged_message_ids: body.message_ids,
      });
    },
  ),
  http.get("*/api/v1/workspaces/:workspaceId/goals", ({ params }) => {
    const workspaceId = String(params.workspaceId);
    return HttpResponse.json({
      items: fixtures.workspaceGoals[workspaceId] ?? [],
    });
  }),
  http.get("*/api/v1/workspaces/:workspaceId/goals/:goalId/messages", ({ params, request }) => {
    const goalId = String(params.goalId);
    const searchParams = new URL(request.url).searchParams;
    const cursor = searchParams.get("cursor");
    const limit = Number.parseInt(searchParams.get("limit") ?? "50", 10);
    const items = fixtures.goalMessages[goalId] ?? [];

    return HttpResponse.json(paginate(items, cursor, limit));
  }),
  http.post(
    "*/api/v1/workspaces/:workspaceId/goals/:goalId/messages",
    async ({ params, request }) => {
      const goalId = String(params.goalId);
      const body = (await request.json()) as GoalMessageRequest;
      const message: GoalMessage = {
        id: createMessageId("goal-message"),
        goal_id: goalId,
        sender_type: "user",
        sender_id: "user-1",
        sender_display_name: "Alex Mercer",
        agent_fqn: null,
        content: body.content,
        originating_interaction_id: null,
        created_at: createIsoNow(),
      };

      fixtures.goalMessages[goalId] = [...(fixtures.goalMessages[goalId] ?? []), message];

      return HttpResponse.json(message, { status: 201 });
    },
  ),
];
