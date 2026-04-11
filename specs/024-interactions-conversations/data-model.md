# Data Model: Interactions and Conversations

**Feature**: 024-interactions-conversations  
**Date**: 2026-04-11  
**Migration**: `009_interactions_conversations.py`

---

## SQLAlchemy Models

### Enums

```python
class InteractionState(str, enum.Enum):
    INITIALIZING = "initializing"
    READY = "ready"
    RUNNING = "running"
    WAITING = "waiting"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELED = "canceled"

class MessageType(str, enum.Enum):
    USER = "user"
    AGENT = "agent"
    SYSTEM = "system"
    INJECTION = "injection"

class ParticipantRole(str, enum.Enum):
    INITIATOR = "initiator"
    RESPONDER = "responder"
    OBSERVER = "observer"

class BranchStatus(str, enum.Enum):
    ACTIVE = "active"
    MERGED = "merged"
    ABANDONED = "abandoned"

class AttentionUrgency(str, enum.Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"

class AttentionStatus(str, enum.Enum):
    PENDING = "pending"
    ACKNOWLEDGED = "acknowledged"
    RESOLVED = "resolved"
    DISMISSED = "dismissed"

# Interaction state machine transitions
INTERACTION_TRANSITIONS: dict[tuple[InteractionState, str], InteractionState] = {
    (InteractionState.INITIALIZING, "ready"): InteractionState.READY,
    (InteractionState.READY, "start"): InteractionState.RUNNING,
    (InteractionState.READY, "cancel"): InteractionState.CANCELED,
    (InteractionState.RUNNING, "wait"): InteractionState.WAITING,
    (InteractionState.RUNNING, "pause"): InteractionState.PAUSED,
    (InteractionState.RUNNING, "complete"): InteractionState.COMPLETED,
    (InteractionState.RUNNING, "fail"): InteractionState.FAILED,
    (InteractionState.RUNNING, "cancel"): InteractionState.CANCELED,
    (InteractionState.WAITING, "resume"): InteractionState.RUNNING,
    (InteractionState.WAITING, "pause"): InteractionState.PAUSED,
    (InteractionState.WAITING, "cancel"): InteractionState.CANCELED,
    (InteractionState.PAUSED, "resume"): InteractionState.RUNNING,
    (InteractionState.PAUSED, "cancel"): InteractionState.CANCELED,
}
```

### Conversation

```python
class Conversation(Base, UUIDMixin, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "conversations"

    workspace_id: Mapped[UUID] = mapped_column(ForeignKey("workspaces.id"), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    created_by: Mapped[str] = mapped_column(String(255), nullable=False)  # user_id or agent FQN
    metadata: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    message_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    __table_args__ = (
        Index("ix_conversations_workspace_created", "workspace_id", "created_at"),
    )
```

### Interaction

```python
class Interaction(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "interactions"

    conversation_id: Mapped[UUID] = mapped_column(ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False, index=True)
    workspace_id: Mapped[UUID] = mapped_column(ForeignKey("workspaces.id"), nullable=False, index=True)
    goal_id: Mapped[UUID | None] = mapped_column(nullable=True, index=True)  # FK to workspace_goals in feature 018
    state: Mapped[InteractionState] = mapped_column(SQLEnum(InteractionState), nullable=False, default=InteractionState.INITIALIZING, index=True)
    state_changed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    error_metadata: Mapped[dict | None] = mapped_column(JSONB, nullable=True)  # set on failure
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        Index("ix_interactions_conversation_state", "conversation_id", "state"),
        Index("ix_interactions_workspace_goal", "workspace_id", "goal_id"),
    )
```

### InteractionMessage

```python
class InteractionMessage(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "interaction_messages"

    interaction_id: Mapped[UUID] = mapped_column(ForeignKey("interactions.id", ondelete="CASCADE"), nullable=False, index=True)
    parent_message_id: Mapped[UUID | None] = mapped_column(ForeignKey("interaction_messages.id"), nullable=True)  # causal DAG
    sender_identity: Mapped[str] = mapped_column(String(255), nullable=False)  # user_id or agent FQN
    message_type: Mapped[MessageType] = mapped_column(SQLEnum(MessageType), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    metadata: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)

    __table_args__ = (
        Index("ix_interaction_messages_interaction_created", "interaction_id", "created_at"),
        Index("ix_interaction_messages_parent", "parent_message_id"),
    )
```

### InteractionParticipant

```python
class InteractionParticipant(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "interaction_participants"

    interaction_id: Mapped[UUID] = mapped_column(ForeignKey("interactions.id", ondelete="CASCADE"), nullable=False, index=True)
    identity: Mapped[str] = mapped_column(String(255), nullable=False)  # user_id or agent FQN
    role: Mapped[ParticipantRole] = mapped_column(SQLEnum(ParticipantRole), nullable=False)
    joined_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    left_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        UniqueConstraint("interaction_id", "identity"),
    )
```

### WorkspaceGoalMessage

```python
class WorkspaceGoalMessage(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "workspace_goal_messages"

    workspace_id: Mapped[UUID] = mapped_column(ForeignKey("workspaces.id"), nullable=False, index=True)
    goal_id: Mapped[UUID] = mapped_column(nullable=False, index=True)  # FK to workspace_goals in feature 018
    participant_identity: Mapped[str] = mapped_column(String(255), nullable=False)  # user_id or agent FQN
    content: Mapped[str] = mapped_column(Text, nullable=False)
    interaction_id: Mapped[UUID | None] = mapped_column(ForeignKey("interactions.id"), nullable=True)  # optional linkage
    metadata: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)

    __table_args__ = (
        Index("ix_workspace_goal_messages_goal_created", "goal_id", "created_at"),
        Index("ix_workspace_goal_messages_workspace_goal", "workspace_id", "goal_id"),
    )
```

### ConversationBranch

```python
class ConversationBranch(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "conversation_branches"

    conversation_id: Mapped[UUID] = mapped_column(ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False, index=True)
    parent_interaction_id: Mapped[UUID] = mapped_column(ForeignKey("interactions.id"), nullable=False)
    branch_interaction_id: Mapped[UUID] = mapped_column(ForeignKey("interactions.id"), nullable=False, unique=True)
    branch_point_message_id: Mapped[UUID] = mapped_column(ForeignKey("interaction_messages.id"), nullable=False)
    status: Mapped[BranchStatus] = mapped_column(SQLEnum(BranchStatus), nullable=False, default=BranchStatus.ACTIVE)

    __table_args__ = (
        Index("ix_conversation_branches_parent", "parent_interaction_id"),
    )
```

### BranchMergeRecord

```python
class BranchMergeRecord(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "branch_merge_records"

    branch_id: Mapped[UUID] = mapped_column(ForeignKey("conversation_branches.id"), nullable=False, index=True)
    merged_by: Mapped[str] = mapped_column(String(255), nullable=False)  # user_id
    conflict_detected: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    conflict_resolution: Mapped[str | None] = mapped_column(Text, nullable=True)
    messages_merged_count: Mapped[int] = mapped_column(Integer, nullable=False)
```

### AttentionRequest

```python
class AttentionRequest(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "attention_requests"

    workspace_id: Mapped[UUID] = mapped_column(ForeignKey("workspaces.id"), nullable=False, index=True)
    source_agent_fqn: Mapped[str] = mapped_column(String(255), nullable=False)
    target_identity: Mapped[str] = mapped_column(String(255), nullable=False, index=True)  # agent FQN or user_id
    urgency: Mapped[AttentionUrgency] = mapped_column(SQLEnum(AttentionUrgency), nullable=False)
    context_summary: Mapped[str] = mapped_column(Text, nullable=False)
    related_execution_id: Mapped[UUID | None] = mapped_column(nullable=True)
    related_interaction_id: Mapped[UUID | None] = mapped_column(ForeignKey("interactions.id"), nullable=True)
    related_goal_id: Mapped[UUID | None] = mapped_column(nullable=True)
    status: Mapped[AttentionStatus] = mapped_column(SQLEnum(AttentionStatus), nullable=False, default=AttentionStatus.PENDING, index=True)
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        Index("ix_attention_requests_target_status", "target_identity", "status"),
    )
```

---

## Pydantic Schemas

### Request Schemas

```python
class ConversationCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=500)
    metadata: dict = Field(default_factory=dict)

class ConversationUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=500)
    metadata: dict | None = None

class InteractionCreate(BaseModel):
    conversation_id: UUID
    goal_id: UUID | None = None

class InteractionTransition(BaseModel):
    trigger: str = Field(..., pattern=r"^(ready|start|wait|resume|pause|complete|fail|cancel)$")
    error_metadata: dict | None = None  # required for "fail" trigger

class MessageCreate(BaseModel):
    content: str = Field(..., min_length=1, max_length=100_000)
    parent_message_id: UUID | None = None
    message_type: MessageType = MessageType.USER
    metadata: dict = Field(default_factory=dict)

class MessageInject(BaseModel):
    content: str = Field(..., min_length=1, max_length=100_000)
    metadata: dict = Field(default_factory=dict)

class ParticipantAdd(BaseModel):
    identity: str = Field(..., min_length=1, max_length=255)
    role: ParticipantRole

class GoalMessageCreate(BaseModel):
    content: str = Field(..., min_length=1, max_length=50_000)
    interaction_id: UUID | None = None
    metadata: dict = Field(default_factory=dict)

class BranchCreate(BaseModel):
    parent_interaction_id: UUID
    branch_point_message_id: UUID

class BranchMerge(BaseModel):
    conflict_resolution: str | None = None

class AttentionRequestCreate(BaseModel):
    target_identity: str = Field(..., min_length=1, max_length=255)
    urgency: AttentionUrgency
    context_summary: str = Field(..., min_length=1, max_length=5_000)
    related_execution_id: UUID | None = None
    related_interaction_id: UUID | None = None
    related_goal_id: UUID | None = None

class AttentionResolve(BaseModel):
    action: Literal["acknowledge", "resolve", "dismiss"]
```

### Response Schemas

```python
class ConversationResponse(BaseModel):
    id: UUID
    workspace_id: UUID
    title: str
    created_by: str
    metadata: dict
    message_count: int
    created_at: datetime
    updated_at: datetime

class InteractionResponse(BaseModel):
    id: UUID
    conversation_id: UUID
    workspace_id: UUID
    goal_id: UUID | None
    state: InteractionState
    state_changed_at: datetime
    error_metadata: dict | None
    started_at: datetime | None
    completed_at: datetime | None
    created_at: datetime

class MessageResponse(BaseModel):
    id: UUID
    interaction_id: UUID
    parent_message_id: UUID | None
    sender_identity: str
    message_type: MessageType
    content: str
    metadata: dict
    created_at: datetime

class ParticipantResponse(BaseModel):
    id: UUID
    interaction_id: UUID
    identity: str
    role: ParticipantRole
    joined_at: datetime
    left_at: datetime | None

class GoalMessageResponse(BaseModel):
    id: UUID
    workspace_id: UUID
    goal_id: UUID
    participant_identity: str
    content: str
    interaction_id: UUID | None
    metadata: dict
    created_at: datetime

class BranchResponse(BaseModel):
    id: UUID
    conversation_id: UUID
    parent_interaction_id: UUID
    branch_interaction_id: UUID
    branch_point_message_id: UUID
    status: BranchStatus
    created_at: datetime

class MergeRecordResponse(BaseModel):
    id: UUID
    branch_id: UUID
    merged_by: str
    conflict_detected: bool
    conflict_resolution: str | None
    messages_merged_count: int
    created_at: datetime

class AttentionRequestResponse(BaseModel):
    id: UUID
    workspace_id: UUID
    source_agent_fqn: str
    target_identity: str
    urgency: AttentionUrgency
    context_summary: str
    related_execution_id: UUID | None
    related_interaction_id: UUID | None
    related_goal_id: UUID | None
    status: AttentionStatus
    acknowledged_at: datetime | None
    resolved_at: datetime | None
    created_at: datetime
```

---

## Service Class Signatures

```python
class InteractionsService:
    # Conversations
    async def create_conversation(
        self, request: ConversationCreate, created_by: str, workspace_id: UUID
    ) -> ConversationResponse: ...
    async def get_conversation(self, conversation_id: UUID, workspace_id: UUID) -> ConversationResponse: ...
    async def list_conversations(
        self, workspace_id: UUID, page: int, page_size: int
    ) -> tuple[list[ConversationResponse], int]: ...
    async def update_conversation(
        self, conversation_id: UUID, request: ConversationUpdate, workspace_id: UUID
    ) -> ConversationResponse: ...
    async def delete_conversation(self, conversation_id: UUID, workspace_id: UUID) -> None: ...

    # Interactions
    async def create_interaction(
        self, request: InteractionCreate, created_by: str, workspace_id: UUID
    ) -> InteractionResponse: ...
    async def get_interaction(self, interaction_id: UUID, workspace_id: UUID) -> InteractionResponse: ...
    async def list_interactions(
        self, conversation_id: UUID, workspace_id: UUID, page: int, page_size: int
    ) -> tuple[list[InteractionResponse], int]: ...
    async def transition_interaction(
        self, interaction_id: UUID, transition: InteractionTransition, workspace_id: UUID
    ) -> InteractionResponse: ...

    # Messages
    async def send_message(
        self, interaction_id: UUID, message: MessageCreate, sender: str, workspace_id: UUID
    ) -> MessageResponse: ...
    async def inject_message(
        self, interaction_id: UUID, injection: MessageInject, sender: str, workspace_id: UUID
    ) -> MessageResponse: ...
    async def list_messages(
        self, interaction_id: UUID, workspace_id: UUID, page: int, page_size: int
    ) -> tuple[list[MessageResponse], int]: ...

    # Participants
    async def add_participant(
        self, interaction_id: UUID, participant: ParticipantAdd, workspace_id: UUID
    ) -> ParticipantResponse: ...
    async def remove_participant(
        self, interaction_id: UUID, identity: str, workspace_id: UUID
    ) -> None: ...
    async def list_participants(
        self, interaction_id: UUID, workspace_id: UUID
    ) -> list[ParticipantResponse]: ...

    # Goals
    async def post_goal_message(
        self, goal_id: UUID, message: GoalMessageCreate, participant: str, workspace_id: UUID
    ) -> GoalMessageResponse: ...
    async def list_goal_messages(
        self, goal_id: UUID, workspace_id: UUID, page: int, page_size: int
    ) -> tuple[list[GoalMessageResponse], int]: ...

    # Branching
    async def create_branch(
        self, request: BranchCreate, workspace_id: UUID
    ) -> BranchResponse: ...
    async def merge_branch(
        self, branch_id: UUID, merge: BranchMerge, merged_by: str, workspace_id: UUID
    ) -> MergeRecordResponse: ...
    async def abandon_branch(
        self, branch_id: UUID, workspace_id: UUID
    ) -> BranchResponse: ...
    async def list_branches(
        self, conversation_id: UUID, workspace_id: UUID
    ) -> list[BranchResponse]: ...

    # Attention
    async def create_attention_request(
        self, request: AttentionRequestCreate, source_agent_fqn: str, workspace_id: UUID
    ) -> AttentionRequestResponse: ...
    async def list_attention_requests(
        self, target_identity: str, workspace_id: UUID, status: AttentionStatus | None, page: int, page_size: int
    ) -> tuple[list[AttentionRequestResponse], int]: ...
    async def resolve_attention_request(
        self, request_id: UUID, action: AttentionResolve, workspace_id: UUID
    ) -> AttentionRequestResponse: ...

    # Internal interfaces (consumed by other bounded contexts)
    async def get_goal_messages(
        self, workspace_id: UUID, goal_id: UUID, limit: int = 100
    ) -> list[GoalMessageResponse]: ...
    async def get_conversation_history(
        self, interaction_id: UUID, limit: int = 50
    ) -> list[MessageResponse]: ...
    async def check_subscription_access(
        self, user_id: str, channel_type: str, channel_id: UUID, workspace_id: UUID
    ) -> bool: ...
```

---

## Kafka Events

### Topic: `interaction.events` (keyed by interaction_id)

```python
class InteractionStartedPayload(BaseModel):
    interaction_id: UUID
    conversation_id: UUID
    workspace_id: UUID
    goal_id: UUID | None
    created_by: str

class InteractionCompletedPayload(BaseModel):
    interaction_id: UUID
    conversation_id: UUID
    workspace_id: UUID
    duration_seconds: float

class InteractionFailedPayload(BaseModel):
    interaction_id: UUID
    conversation_id: UUID
    workspace_id: UUID
    error_metadata: dict

class InteractionCanceledPayload(BaseModel):
    interaction_id: UUID
    conversation_id: UUID
    workspace_id: UUID

class MessageReceivedPayload(BaseModel):
    message_id: UUID
    interaction_id: UUID
    conversation_id: UUID
    workspace_id: UUID
    sender_identity: str
    message_type: MessageType

class BranchMergedPayload(BaseModel):
    branch_id: UUID
    parent_interaction_id: UUID
    branch_interaction_id: UUID
    conversation_id: UUID
    workspace_id: UUID
    conflict_detected: bool
```

### Topic: `workspace.goal` (keyed by workspace_id)

```python
class GoalMessagePostedPayload(BaseModel):
    message_id: UUID
    goal_id: UUID
    workspace_id: UUID
    participant_identity: str
    interaction_id: UUID | None

class GoalStatusChangedPayload(BaseModel):
    goal_id: UUID
    workspace_id: UUID
    old_status: str
    new_status: str
```

### Topic: `interaction.attention` (keyed by target_identity)

```python
class AttentionRequestedPayload(BaseModel):
    attention_request_id: UUID
    workspace_id: UUID
    source_agent_fqn: str
    target_identity: str
    urgency: AttentionUrgency
    context_summary: str
    related_execution_id: UUID | None
    related_interaction_id: UUID | None
    related_goal_id: UUID | None
```
