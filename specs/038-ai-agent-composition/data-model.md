# Data Model: AI-Assisted Agent Composition

**Feature**: 038-ai-agent-composition  
**Storage**: PostgreSQL 16 (5 tables)

---

## PostgreSQL Tables

### 1. `composition_requests`

Root record for a composition request. Every blueprint and audit entry links back to this.

```python
class CompositionRequest(Base, UUIDMixin, TimestampMixin, WorkspaceScopedMixin):
    __tablename__ = "composition_requests"

    request_type: Mapped[str]           # "agent" | "fleet"
    description: Mapped[str]            # Original natural-language description
    requested_by: Mapped[UUID]          # FK → auth.users.id (operator identity)
    status: Mapped[str]                 # "pending" | "completed" | "failed"
    llm_model_used: Mapped[str | None]  # Model identifier used for generation
    generation_time_ms: Mapped[int | None]  # Time to generate in milliseconds

    # Relationships
    agent_blueprint: Mapped["AgentBlueprint | None"] = relationship(back_populates="request")
    fleet_blueprint: Mapped["FleetBlueprint | None"] = relationship(back_populates="request")
    audit_entries: Mapped[list["CompositionAuditEntry"]] = relationship(back_populates="request")

    __table_args__ = (
        Index("ix_composition_requests_workspace_status", "workspace_id", "status"),
        Index("ix_composition_requests_workspace_type", "workspace_id", "request_type"),
        CheckConstraint("request_type IN ('agent', 'fleet')", name="ck_request_type"),
        CheckConstraint("status IN ('pending', 'completed', 'failed')", name="ck_request_status"),
    )
```

---

### 2. `composition_agent_blueprints`

AI-generated agent configuration proposal. JSONB for flexible nested structures.

```python
class AgentBlueprint(Base, UUIDMixin, TimestampMixin, WorkspaceScopedMixin):
    __tablename__ = "composition_agent_blueprints"

    request_id: Mapped[UUID]            # FK → composition_requests.id (unique)
    version: Mapped[int]                # 1 = original AI generation; increments on override
    model_config: Mapped[dict]          # JSONB: {model_id, temperature, max_tokens, reasoning_mode}
    tool_selections: Mapped[list]       # JSONB: [{tool_name, tool_id, relevance_justification, status}]
    connector_suggestions: Mapped[list] # JSONB: [{connector_type, connector_name, purpose, status}]
    policy_recommendations: Mapped[list]# JSONB: [{policy_id, policy_name, attachment_reason}]
    context_profile: Mapped[dict]       # JSONB: {assembly_strategy, memory_scope, knowledge_sources}
    maturity_estimate: Mapped[str]      # "experimental" | "developing" | "production_ready"
    maturity_reasoning: Mapped[str]     # Plain text rationale
    confidence_score: Mapped[float]     # 0.0–1.0 (LLM self-assessed)
    low_confidence: Mapped[bool]        # True if confidence_score < 0.5
    follow_up_questions: Mapped[list]   # JSONB: [{question, context}] — populated when low_confidence
    llm_reasoning_summary: Mapped[str]  # LLM's explanation of choices (for audit trail)
    alternatives_considered: Mapped[list] # JSONB: [{field, alternatives, reason_rejected}]

    # Relationships
    request: Mapped["CompositionRequest"] = relationship(back_populates="agent_blueprint")
    validations: Mapped[list["CompositionValidation"]] = relationship(back_populates="agent_blueprint")

    __table_args__ = (
        UniqueConstraint("request_id", name="uq_agent_blueprint_request"),
        Index("ix_agent_blueprints_workspace", "workspace_id"),
        CheckConstraint(
            "maturity_estimate IN ('experimental', 'developing', 'production_ready')",
            name="ck_maturity_estimate"
        ),
        CheckConstraint("confidence_score >= 0.0 AND confidence_score <= 1.0", name="ck_confidence_range"),
    )
```

---

### 3. `composition_fleet_blueprints`

AI-generated fleet configuration proposal.

```python
class FleetBlueprint(Base, UUIDMixin, TimestampMixin, WorkspaceScopedMixin):
    __tablename__ = "composition_fleet_blueprints"

    request_id: Mapped[UUID]            # FK → composition_requests.id (unique)
    version: Mapped[int]                # 1 = original AI generation; increments on override
    topology_type: Mapped[str]          # "sequential" | "hierarchical" | "peer" | "hybrid"
    member_count: Mapped[int]           # Number of agents in the fleet
    member_roles: Mapped[list]          # JSONB: [{role_name, purpose, agent_blueprint_inline: {...}}]
    orchestration_rules: Mapped[list]   # JSONB: [{rule_type, trigger, action, target_role}]
    delegation_rules: Mapped[list]      # JSONB: [{from_role, to_role, trigger_condition}]
    escalation_rules: Mapped[list]      # JSONB: [{from_role, to_role, trigger_condition, urgency}]
    confidence_score: Mapped[float]     # 0.0–1.0
    low_confidence: Mapped[bool]
    follow_up_questions: Mapped[list]   # JSONB
    llm_reasoning_summary: Mapped[str]
    alternatives_considered: Mapped[list] # JSONB
    single_agent_suggestion: Mapped[bool] # True when LLM suggests agent is sufficient (no fleet needed)

    # Relationships
    request: Mapped["CompositionRequest"] = relationship(back_populates="fleet_blueprint")
    validations: Mapped[list["CompositionValidation"]] = relationship(back_populates="fleet_blueprint")

    __table_args__ = (
        UniqueConstraint("request_id", name="uq_fleet_blueprint_request"),
        Index("ix_fleet_blueprints_workspace", "workspace_id"),
        CheckConstraint(
            "topology_type IN ('sequential', 'hierarchical', 'peer', 'hybrid')",
            name="ck_topology_type"
        ),
    )
```

---

### 4. `composition_validations`

Validation results for a blueprint. Multiple validations per blueprint (first generation + re-validation after overrides).

```python
class CompositionValidation(Base, UUIDMixin, TimestampMixin, WorkspaceScopedMixin):
    __tablename__ = "composition_validations"

    # At most one of these is set
    agent_blueprint_id: Mapped[UUID | None]  # FK → composition_agent_blueprints.id
    fleet_blueprint_id: Mapped[UUID | None]  # FK → composition_fleet_blueprints.id

    overall_valid: Mapped[bool]
    tools_check_passed: Mapped[bool]
    tools_check_details: Mapped[dict]   # JSONB: [{tool_name, status, remediation?}]
    model_check_passed: Mapped[bool]
    model_check_details: Mapped[dict]   # JSONB: {model_id, status, remediation?}
    connectors_check_passed: Mapped[bool]
    connectors_check_details: Mapped[dict]  # JSONB: [{connector_name, status, remediation?}]
    policy_check_passed: Mapped[bool]
    policy_check_details: Mapped[dict]  # JSONB: [{policy_id, status, conflicts?}]
    cycle_check_passed: Mapped[bool | None]  # NULL for agent blueprints (fleet-only)
    cycle_check_details: Mapped[dict | None] # JSONB: {cycles_found: [{path}]}

    __table_args__ = (
        CheckConstraint(
            "(agent_blueprint_id IS NOT NULL) != (fleet_blueprint_id IS NOT NULL)",
            name="ck_one_blueprint_ref"
        ),
        Index("ix_validations_agent_blueprint", "agent_blueprint_id"),
        Index("ix_validations_fleet_blueprint", "fleet_blueprint_id"),
    )
```

---

### 5. `composition_audit_entries`

**Append-only**. No UPDATE or DELETE. Records every composition lifecycle event.

```python
class CompositionAuditEntry(Base, UUIDMixin, WorkspaceScopedMixin):
    __tablename__ = "composition_audit_entries"
    # NO updated_at — this table is append-only

    created_at: Mapped[datetime]         # Explicit (not from TimestampMixin to avoid updated_at)
    request_id: Mapped[UUID]             # FK → composition_requests.id
    event_type: Mapped[str]              # "blueprint_generated" | "blueprint_validated" |
                                         # "blueprint_overridden" | "blueprint_finalized" | "generation_failed"
    actor_id: Mapped[UUID | None]        # FK → auth.users.id (None for system-generated events)
    payload: Mapped[dict]                # JSONB: event-specific data (override details, validation summary, etc.)

    __table_args__ = (
        Index("ix_audit_entries_request_id", "request_id"),
        Index("ix_audit_entries_workspace_created", "workspace_id", "created_at"),
        CheckConstraint(
            "event_type IN ('blueprint_generated', 'blueprint_validated', "
            "'blueprint_overridden', 'blueprint_finalized', 'generation_failed')",
            name="ck_audit_event_type"
        ),
    )
```

---

## State Transitions

### CompositionRequest.status

```
pending → completed   (blueprint successfully generated)
pending → failed      (LLM unavailable or parse error)
```

### AgentBlueprint / FleetBlueprint.version

```
1 (AI generated)
→ 2 (after first human override)
→ 3 (after second human override)
→ ...  (monotonically incrementing, old versions not deleted)
```

Note: Overrides create a **new version record** rather than mutating the existing one, preserving full override history.

---

## ClickHouse

No ClickHouse table required for this feature. Blueprint composition is not a time-series analytics workload. Audit queries are OLTP cursor-paginated reads (PostgreSQL is appropriate).

---

## Kafka Event Schema

**Topic**: `composition.events`  
**Key**: `composition_request_id` (string UUID)

```json
{
  "event_id": "uuid",
  "event_type": "blueprint_generated | blueprint_validated | blueprint_overridden | generation_failed",
  "composition_request_id": "uuid",
  "workspace_id": "uuid",
  "request_type": "agent | fleet",
  "actor_id": "uuid | null",
  "timestamp": "ISO8601",
  "payload": {}
}
```
