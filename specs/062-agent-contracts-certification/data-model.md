# Data Model: Agent Contracts and Certification Enhancements

**Feature**: 062-agent-contracts-certification  
**Migration**: 049 (`apps/control-plane/migrations/versions/049_agent_contracts_and_certification.py`)

---

## Migration 049 — DDL Summary

### New Tables

```sql
-- Platform-level certifier registry (no workspace scope)
CREATE TABLE certifiers (
    id          UUID        NOT NULL DEFAULT gen_random_uuid() PRIMARY KEY,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_by  UUID,
    updated_by  UUID,
    name        VARCHAR(256) NOT NULL,
    organization VARCHAR(256),
    credentials JSONB,
    permitted_scopes JSONB,   -- array of scope strings
    is_active   BOOLEAN NOT NULL DEFAULT TRUE
);

-- Machine-enforceable agent contracts
CREATE TABLE agent_contracts (
    id                      UUID        NOT NULL DEFAULT gen_random_uuid() PRIMARY KEY,
    created_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_by              UUID,
    updated_by              UUID,
    workspace_id            UUID        NOT NULL REFERENCES workspaces_workspaces(id),
    agent_id                VARCHAR(512) NOT NULL,     -- FQN string (not FK, preserves audit on deletion)
    task_scope              TEXT        NOT NULL,
    expected_outputs        JSONB,
    quality_thresholds      JSONB,                     -- {accuracy_min: 0.95, latency_max_ms: 5000}
    time_constraint_seconds INTEGER,
    cost_limit_tokens       INTEGER,
    escalation_conditions   JSONB,
    success_criteria        JSONB,
    enforcement_policy      VARCHAR(32) NOT NULL DEFAULT 'warn', -- warn/throttle/escalate/terminate
    is_archived             BOOLEAN     NOT NULL DEFAULT FALSE
);

CREATE INDEX ix_agent_contracts_workspace_id ON agent_contracts(workspace_id);
CREATE INDEX ix_agent_contracts_agent_id ON agent_contracts(agent_id);

-- Audit trail for contract term violations
CREATE TABLE contract_breach_events (
    id                  UUID        NOT NULL DEFAULT gen_random_uuid() PRIMARY KEY,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    contract_id         UUID        REFERENCES agent_contracts(id) ON DELETE SET NULL,
    target_type         VARCHAR(32) NOT NULL,   -- "interaction" or "execution"
    target_id           UUID        NOT NULL,
    breached_term       VARCHAR(64) NOT NULL,   -- "time_constraint" / "cost_limit" / "quality_threshold" / "escalation"
    observed_value      JSONB       NOT NULL,
    threshold_value     JSONB       NOT NULL,
    enforcement_action  VARCHAR(32) NOT NULL,   -- warn/throttle/escalate/terminate
    enforcement_outcome VARCHAR(32) NOT NULL,   -- success/failed
    contract_snapshot   JSONB       NOT NULL    -- full contract terms at attachment time
);

CREATE INDEX ix_contract_breach_events_contract_id ON contract_breach_events(contract_id);
CREATE INDEX ix_contract_breach_events_target ON contract_breach_events(target_type, target_id);
CREATE INDEX ix_contract_breach_events_created_at ON contract_breach_events(created_at);

-- Surveillance reassessment verdicts
CREATE TABLE reassessment_records (
    id                UUID        NOT NULL DEFAULT gen_random_uuid() PRIMARY KEY,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_by        UUID,
    updated_by        UUID,
    certification_id  UUID        NOT NULL REFERENCES trust_certifications(id) ON DELETE CASCADE,
    verdict           VARCHAR(32) NOT NULL,  -- "pass" / "fail" / "action_required"
    reassessor_id     VARCHAR(255) NOT NULL, -- user id or "automated"
    notes             TEXT
);

CREATE INDEX ix_reassessment_records_certification_id ON reassessment_records(certification_id);

-- Material-change recertification requests (distinct from existing recertification_triggers)
CREATE TABLE trust_recertification_requests (
    id                      UUID        NOT NULL DEFAULT gen_random_uuid() PRIMARY KEY,
    created_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
    certification_id        UUID        NOT NULL REFERENCES trust_certifications(id) ON DELETE CASCADE,
    trigger_type            VARCHAR(32) NOT NULL,   -- "revision" / "policy" / "signal"
    trigger_reference       TEXT        NOT NULL,   -- ID/description of triggering change
    deadline                TIMESTAMPTZ,            -- grace period expiry; NULL = no deadline
    resolution_status       VARCHAR(32) NOT NULL DEFAULT 'pending', -- pending/resolved/dismissed/revoked
    dismissal_justification TEXT                    -- required if resolution_status = dismissed
);

CREATE INDEX ix_trust_recertification_requests_certification_id
    ON trust_recertification_requests(certification_id);
CREATE INDEX ix_trust_recertification_requests_deadline
    ON trust_recertification_requests(deadline)
    WHERE resolution_status = 'pending';
```

### Enum Extensions

```sql
-- Extend existing certification_status enum (Brownfield Rule 6 — additive only)
ALTER TYPE certification_status ADD VALUE IF NOT EXISTS 'expiring' BEFORE 'expired';
ALTER TYPE certification_status ADD VALUE IF NOT EXISTS 'suspended';
```

### Altered Tables

```sql
-- trust/models.py: TrustCertification gets certifier FK and reassessment schedule
ALTER TABLE trust_certifications
    ADD COLUMN external_certifier_id UUID REFERENCES certifiers(id) ON DELETE SET NULL,
    ADD COLUMN reassessment_schedule VARCHAR(64);   -- cron expression, nullable

-- interactions/models.py: opt-in contract attachment
ALTER TABLE interactions
    ADD COLUMN contract_id       UUID REFERENCES agent_contracts(id) ON DELETE SET NULL,
    ADD COLUMN contract_snapshot JSONB;            -- captured at attachment time

-- execution/models.py: opt-in contract attachment
ALTER TABLE executions
    ADD COLUMN contract_id       UUID REFERENCES agent_contracts(id) ON DELETE SET NULL,
    ADD COLUMN contract_snapshot JSONB;            -- captured at attachment time

CREATE INDEX ix_interactions_contract_id ON interactions(contract_id)
    WHERE contract_id IS NOT NULL;
CREATE INDEX ix_executions_contract_id ON executions(contract_id)
    WHERE contract_id IS NOT NULL;
```

---

## SQLAlchemy Models

### New in `apps/control-plane/src/platform/trust/models.py`

```python
# ----------- Add after existing TrustCertification model -----------

class Certifier(Base, UUIDMixin, TimestampMixin, AuditMixin):
    __tablename__ = "certifiers"

    name: Mapped[str] = mapped_column(String(256), nullable=False)
    organization: Mapped[str | None] = mapped_column(String(256))
    credentials: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    permitted_scopes: Mapped[list[str] | None] = mapped_column(JSONB)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    certifications: Mapped[list["TrustCertification"]] = relationship(
        back_populates="certifier",
    )


class AgentContract(Base, UUIDMixin, TimestampMixin, AuditMixin, WorkspaceScopedMixin):
    __tablename__ = "agent_contracts"

    agent_id: Mapped[str] = mapped_column(String(512), nullable=False, index=True)
    task_scope: Mapped[str] = mapped_column(Text, nullable=False)
    expected_outputs: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    quality_thresholds: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    time_constraint_seconds: Mapped[int | None] = mapped_column(Integer)
    cost_limit_tokens: Mapped[int | None] = mapped_column(Integer)
    escalation_conditions: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    success_criteria: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    enforcement_policy: Mapped[str] = mapped_column(
        String(32), nullable=False, default="warn"
    )
    is_archived: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    breach_events: Mapped[list["ContractBreachEvent"]] = relationship(
        back_populates="contract",
        cascade="all, delete-orphan",
    )


class ContractBreachEvent(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "contract_breach_events"

    contract_id: Mapped[UUID | None] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("agent_contracts.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    target_type: Mapped[str] = mapped_column(String(32), nullable=False)
    target_id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), nullable=False)
    breached_term: Mapped[str] = mapped_column(String(64), nullable=False)
    observed_value: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    threshold_value: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    enforcement_action: Mapped[str] = mapped_column(String(32), nullable=False)
    enforcement_outcome: Mapped[str] = mapped_column(String(32), nullable=False)
    contract_snapshot: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)

    contract: Mapped["AgentContract | None"] = relationship(
        back_populates="breach_events",
    )


class ReassessmentRecord(Base, UUIDMixin, TimestampMixin, AuditMixin):
    __tablename__ = "reassessment_records"

    certification_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("trust_certifications.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    verdict: Mapped[str] = mapped_column(String(32), nullable=False)
    reassessor_id: Mapped[str] = mapped_column(String(255), nullable=False)
    notes: Mapped[str | None] = mapped_column(Text)

    certification: Mapped["TrustCertification"] = relationship(
        back_populates="reassessment_records",
    )


class TrustRecertificationRequest(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "trust_recertification_requests"

    certification_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("trust_certifications.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    trigger_type: Mapped[str] = mapped_column(String(32), nullable=False)
    trigger_reference: Mapped[str] = mapped_column(Text, nullable=False)
    deadline: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    resolution_status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="pending"
    )
    dismissal_justification: Mapped[str | None] = mapped_column(Text)

    certification: Mapped["TrustCertification"] = relationship(
        back_populates="recertification_requests",
    )
```

### Additions to existing `TrustCertification` in `trust/models.py`

```python
# Add these columns to the existing TrustCertification class:
external_certifier_id: Mapped[UUID | None] = mapped_column(
    PgUUID(as_uuid=True),
    ForeignKey("certifiers.id", ondelete="SET NULL"),
    nullable=True,
)
reassessment_schedule: Mapped[str | None] = mapped_column(String(64))

# Add these relationships:
certifier: Mapped["Certifier | None"] = relationship(
    back_populates="certifications",
)
reassessment_records: Mapped[list["ReassessmentRecord"]] = relationship(
    back_populates="certification",
    cascade="all, delete-orphan",
)
recertification_requests: Mapped[list["TrustRecertificationRequest"]] = relationship(
    back_populates="certification",
    cascade="all, delete-orphan",
)
```

### Additions to `interactions/models.py`

```python
# Add to Interaction class:
contract_id: Mapped[UUID | None] = mapped_column(
    PgUUID(as_uuid=True),
    ForeignKey("agent_contracts.id", ondelete="SET NULL"),
    nullable=True,
)
contract_snapshot: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
```

### Additions to `execution/models.py`

```python
# Add to Execution class:
contract_id: Mapped[UUID | None] = mapped_column(
    PgUUID(as_uuid=True),
    ForeignKey("agent_contracts.id", ondelete="SET NULL"),
    nullable=True,
)
contract_snapshot: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
```

### `CertificationStatus` enum extension (in `trust/models.py`)

```python
# Extend the existing CertificationStatus StrEnum:
class CertificationStatus(StrEnum):
    pending    = "pending"
    active     = "active"
    expiring   = "expiring"    # NEW — approaching expiry
    expired    = "expired"
    suspended  = "suspended"   # NEW — material-change suspension
    revoked    = "revoked"
    superseded = "superseded"
```

---

## Pydantic Schemas

### New file: `apps/control-plane/src/platform/trust/contract_schemas.py`

```python
# CertifierCreate, CertifierResponse, CertifierUpdate
class CertifierCreate(BaseModel):
    name: str
    organization: str | None = None
    credentials: dict[str, Any] | None = None
    permitted_scopes: list[str] = []

class CertifierResponse(BaseModel):
    id: UUID
    created_at: datetime
    name: str
    organization: str | None
    credentials: dict[str, Any] | None
    permitted_scopes: list[str]
    is_active: bool
    model_config = ConfigDict(from_attributes=True)

# AgentContractCreate, AgentContractResponse, AgentContractUpdate
class AgentContractCreate(BaseModel):
    agent_id: str  # FQN
    task_scope: str
    expected_outputs: dict[str, Any] | None = None
    quality_thresholds: dict[str, Any] | None = None
    time_constraint_seconds: int | None = Field(None, ge=1)
    cost_limit_tokens: int | None = Field(None, ge=1)
    escalation_conditions: dict[str, Any] | None = None
    success_criteria: dict[str, Any] | None = None
    enforcement_policy: Literal["warn", "throttle", "escalate", "terminate"] = "warn"

class AgentContractResponse(BaseModel):
    id: UUID
    created_at: datetime
    workspace_id: UUID
    agent_id: str
    task_scope: str
    expected_outputs: dict[str, Any] | None
    quality_thresholds: dict[str, Any] | None
    time_constraint_seconds: int | None
    cost_limit_tokens: int | None
    escalation_conditions: dict[str, Any] | None
    success_criteria: dict[str, Any] | None
    enforcement_policy: str
    is_archived: bool
    model_config = ConfigDict(from_attributes=True)

# ContractBreachEventResponse
class ContractBreachEventResponse(BaseModel):
    id: UUID
    created_at: datetime
    contract_id: UUID | None
    target_type: str
    target_id: UUID
    breached_term: str
    observed_value: dict[str, Any]
    threshold_value: dict[str, Any]
    enforcement_action: str
    enforcement_outcome: str
    model_config = ConfigDict(from_attributes=True)

# ReassessmentRecordCreate, ReassessmentRecordResponse
class ReassessmentCreate(BaseModel):
    verdict: Literal["pass", "fail", "action_required"]
    notes: str | None = None

class ReassessmentResponse(BaseModel):
    id: UUID
    created_at: datetime
    certification_id: UUID
    verdict: str
    reassessor_id: str
    notes: str | None
    model_config = ConfigDict(from_attributes=True)

# ComplianceRateQuery, ComplianceRateResponse
class ComplianceRateQuery(BaseModel):
    scope: Literal["agent", "fleet", "workspace"]
    scope_id: str
    start: datetime
    end: datetime
    bucket: Literal["hourly", "daily"] = "daily"

class ComplianceRateResponse(BaseModel):
    scope: str
    scope_id: str
    start: datetime
    end: datetime
    total_contract_attached: int
    compliant: int
    warned: int
    throttled: int
    escalated: int
    terminated: int
    compliance_rate: float | None  # None when total_contract_attached == 0
    breach_by_term: dict[str, int]  # {time_constraint: N, cost_limit: N, ...}
    trend: list[dict[str, Any]]  # time-bucketed series

# DismissSuspensionRequest
class DismissSuspensionRequest(BaseModel):
    justification: str = Field(..., min_length=10)
```

---

## Service Interfaces

### `trust/contract_service.py` — ContractService

```python
class ContractService:
    async def create_contract(
        self, data: AgentContractCreate, workspace_id: UUID, actor_id: str
    ) -> AgentContractResponse: ...

    async def get_contract(self, contract_id: UUID) -> AgentContractResponse: ...

    async def list_contracts(
        self, workspace_id: UUID, agent_id: str | None = None, include_archived: bool = False
    ) -> list[AgentContractResponse]: ...

    async def update_contract(
        self, contract_id: UUID, data: AgentContractUpdate, actor_id: str
    ) -> AgentContractResponse: ...

    async def archive_contract(self, contract_id: UUID, actor_id: str) -> None: ...

    async def attach_to_interaction(
        self, interaction_id: UUID, contract_id: UUID
    ) -> None:
        """Idempotent. Captures contract snapshot at attachment time."""

    async def attach_to_execution(
        self, execution_id: UUID, contract_id: UUID
    ) -> None:
        """Idempotent. Captures contract snapshot at attachment time."""

    async def get_compliance_rates(
        self, query: ComplianceRateQuery, workspace_id: UUID
    ) -> ComplianceRateResponse: ...
```

### `trust/contract_monitor.py` — ContractMonitorConsumer

```python
class ContractMonitorConsumer:
    def register(self, manager: EventConsumerManager) -> None:
        manager.subscribe("workflow.runtime", f"{...}.trust-contract-monitor", self.handle_event)
        manager.subscribe("runtime.lifecycle", f"{...}.trust-contract-monitor-lifecycle", self.handle_event)

    async def handle_event(self, envelope: EventEnvelope) -> None:
        """Evaluates execution telemetry against attached contract terms.
        Emits ContractBreachEvent and triggers enforcement on violation."""

    async def _evaluate_cost(self, execution_id, snapshot, token_count) -> BreachResult | None: ...
    async def _evaluate_time(self, execution_id, snapshot, elapsed_seconds) -> BreachResult | None: ...
    async def _enforce(self, breach: BreachResult, target_type, target_id, snapshot) -> str: ...
```

### `trust/surveillance_service.py` — SurveillanceService

```python
class SurveillanceService:
    async def run_surveillance_cycle(self) -> None:
        """APScheduler job: evaluate expiry approach, expired, and reassessment schedules."""

    async def check_grace_period_expiry(self) -> None:
        """APScheduler job: transition suspended certs past deadline to revoked."""

    async def handle_material_change(
        self, envelope: EventEnvelope
    ) -> None:
        """Kafka event handler: suspend active/expiring certifications on material change."""

    def register(self, manager: EventConsumerManager) -> None:
        manager.subscribe("policy.events", f"{...}.trust-surveillance-material-change", self.handle_material_change)
        manager.subscribe("trust.events", f"{...}.trust-surveillance-revision-signals", self.handle_material_change)
```

### Modifications to `trust/service.py` — CertificationService

```python
# New methods added to existing CertificationService:

async def issue_with_certifier(
    self, cert_id: UUID, certifier_id: UUID, scope: str, actor_id: str
) -> CertificationResponse:
    """Links external certifier to certification. Validates scope is in certifier.permitted_scopes."""

async def dismiss_suspension(
    self, cert_id: UUID, justification: str, actor_id: str
) -> CertificationResponse:
    """FR-024: Operator manually dismisses material-change suspension with audit note."""

async def expire_stale(self) -> int:
    """EXTENDED: now also handles expiring → expired transition in addition to active → expired."""
```
