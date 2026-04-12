export type MessageSenderType = "user" | "agent" | "system";

export type MessageStatus = "streaming" | "complete" | "failed";

export type InteractionState =
  | "active"
  | "completed"
  | "failed"
  | "awaiting_approval"
  | "cancelled";

export type ReasoningMode = "chain_of_thought" | "tree_of_thought" | "none";

export type BranchStatus = "active" | "merged" | "abandoned";

export type GoalStatus = "active" | "paused" | "completed" | "abandoned";

export interface MessageAttachment {
  id: string;
  filename: string;
  mime_type: string;
  size_bytes: number;
  url: string;
}

export interface Message {
  id: string;
  conversation_id: string;
  interaction_id: string;
  sender_type: MessageSenderType;
  sender_id: string;
  sender_display_name: string;
  content: string;
  attachments: MessageAttachment[];
  status: MessageStatus;
  is_mid_process_injection: boolean;
  branch_origin: string | null;
  created_at: string;
  updated_at: string;
}

export interface Interaction {
  id: string;
  conversation_id: string;
  agent_id: string;
  agent_fqn: string;
  agent_display_name: string;
  state: InteractionState;
  reasoning_mode: ReasoningMode;
  self_correction_count: number;
  created_at: string;
  updated_at: string;
}

export interface ConversationBranch {
  id: string;
  conversation_id: string;
  name: string;
  description: string | null;
  originating_message_id: string;
  status: BranchStatus;
  created_at: string;
}

export interface Conversation {
  id: string;
  workspace_id: string;
  title: string;
  created_at: string;
  interactions: Interaction[];
  branches: ConversationBranch[];
}

export interface WorkspaceGoal {
  id: string;
  workspace_id: string;
  title: string;
  description: string | null;
  status: GoalStatus;
  created_at: string;
}

export interface GoalMessage {
  id: string;
  goal_id: string;
  sender_type: MessageSenderType;
  sender_id: string;
  sender_display_name: string;
  agent_fqn: string | null;
  content: string;
  originating_interaction_id: string | null;
  created_at: string;
}

export interface PaginatedMessageResponse<TMessage> {
  items: TMessage[];
  next_cursor: string | null;
}

export interface ConversationListResponse {
  items: Conversation[];
}

export interface ConversationResponse extends Conversation {}

export interface BranchCreateRequest {
  name: string;
  description?: string;
  originating_message_id: string;
}

export interface BranchMergeRequest {
  message_ids: string[];
}

export interface SendMessageRequest {
  content: string;
  is_mid_process_injection: boolean;
}

export interface GoalMessageRequest {
  content: string;
}

export interface WsMessageCreated {
  event_type: "message.created";
  message: Message;
}

export interface WsMessageStreamed {
  event_type: "message.streamed";
  message_id: string;
  interaction_id: string;
  delta: string;
}

export interface WsMessageCompleted {
  event_type: "message.completed";
  message: Message;
}

export interface WsTypingStarted {
  event_type: "typing.started";
  interaction_id: string;
  agent_fqn: string;
}

export interface WsTypingStopped {
  event_type: "typing.stopped";
  interaction_id: string;
}

export interface WsInteractionStateChanged {
  event_type: "interaction.state_changed";
  interaction: Interaction;
}

export interface WsBranchCreated {
  event_type: "branch.created";
  branch: ConversationBranch;
}

export interface WsBranchMerged {
  event_type: "branch.merged";
  branch_id: string;
  merged_message_ids: string[];
}

export interface WsGoalMessageCreated {
  event_type: "goal.message_created";
  message: GoalMessage;
}

export interface WsGoalStateChanged {
  event_type: "goal.state_changed";
  goal: WorkspaceGoal;
}

export type ConversationEventPayload =
  | WsMessageCreated
  | WsMessageStreamed
  | WsMessageCompleted
  | WsTypingStarted
  | WsTypingStopped
  | WsInteractionStateChanged
  | WsBranchCreated
  | WsBranchMerged;

export type GoalEventPayload = WsGoalMessageCreated | WsGoalStateChanged;

export const queryKeys = {
  conversationList: (workspaceId: string) =>
    ["conversation-list", workspaceId] as const,
  conversation: (id: string) => ["conversation", id] as const,
  messages: (
    conversationId: string,
    branchId: string | null,
    interactionId?: string | null,
  ) =>
    [
      "messages",
      conversationId,
      branchId ?? "main",
      interactionId ?? "all-interactions",
    ] as const,
  interaction: (id: string) => ["interaction", id] as const,
  goals: (workspaceId: string) => ["goals", workspaceId] as const,
  goalMessages: (goalId: string) => ["goal-messages", goalId] as const,
};

export function formatReasoningMode(reasoningMode: ReasoningMode): string {
  switch (reasoningMode) {
    case "chain_of_thought":
      return "Chain of Thought";
    case "tree_of_thought":
      return "Tree of Thought";
    default:
      return "—";
  }
}

export function isTerminalGoalStatus(status: GoalStatus): boolean {
  return status === "completed" || status === "abandoned";
}
