# Data Model: Advanced Reasoning Modes and Trace Export

**Branch**: `064-reasoning-modes-and-trace` | **Date**: 2026-04-19  
**Feature**: [spec.md](spec.md) | **Research**: [research.md](research.md)

## 1. Proto Contract Changes

### 1.1 ReasoningMode

```protobuf
enum ReasoningMode {
  REASONING_MODE_UNSPECIFIED = 0;
  DIRECT = 1;
  CHAIN_OF_THOUGHT = 2;
  TREE_OF_THOUGHT = 3;
  REACT = 4;
  CODE_AS_REASONING = 5;
  DEBATE = 6;
  SELF_CORRECTION = 7;
}
```

### 1.2 SelectReasoningModeRequest

```protobuf
message SelectReasoningModeRequest {
  string execution_id = 1;
  string task_brief = 2;
  string forced_mode = 3;
  BudgetConstraints budget_constraints = 4;
  optional double compute_budget = 7; // omitted = unconstrained; explicit 0 is invalid
}
```

### 1.3 Debate session RPCs

```protobuf
rpc StartDebateSession(StartDebateSessionRequest) returns (DebateSessionHandle);
rpc SubmitDebateTurn(SubmitDebateTurnRequest) returns (DebateRoundResult);
rpc FinalizeDebateSession(FinalizeDebateSessionRequest) returns (DebateSessionResult);

message StartDebateSessionRequest {
  string execution_id = 1;
  string debate_id = 2;
  repeated string participant_fqns = 3;
  int32 round_limit = 4;
  int64 per_turn_timeout_ms = 5;
  optional double compute_budget = 6;
  double consensus_epsilon = 7;
}

message SubmitDebateTurnRequest {
  string debate_id = 1;
  string agent_fqn = 2;
  string step_type = 3; // position | critique | rebuttal | synthesis
  string content = 4;
  double quality_score = 5;
  int64 tokens_used = 6;
  google.protobuf.Timestamp occurred_at = 7;
}

message DebateSessionHandle {
  string execution_id = 1;
  string debate_id = 2;
  string status = 3;
  int32 current_round = 4;
}

message DebateRoundResult {
  string debate_id = 1;
  int32 round_number = 2;
  string consensus_status = 3;
  bool debate_complete = 4;
  double compute_budget_used = 5;
  bool compute_budget_exhausted = 6;
}

message FinalizeDebateSessionRequest {
  string debate_id = 1;
}

message DebateSessionResult {
  string execution_id = 1;
  string debate_id = 2;
  string status = 3;
  bool consensus_reached = 4;
  double compute_budget_used = 5;
  bool compute_budget_exhausted = 6;
  string storage_key = 7;
}
```

### 1.4 SELF_CORRECTION payload extensions

```protobuf
message StartSelfCorrectionRequest {
  string loop_id = 1;
  string execution_id = 2;
  int32 max_iterations = 3;
  double cost_cap = 4;
  double epsilon = 5;
  bool escalate_on_budget_exceeded = 6;
  string step_id = 7;
  optional double compute_budget = 8;
  double degradation_threshold = 9;
}

message CorrectionIterationEvent {
  string loop_id = 1;
  double quality_score = 2;
  double cost = 3;
  int64 duration_ms = 4;
  string prior_answer = 5;
  string critique = 6;
  string refined_answer = 7;
  int32 iteration_num = 8;
}
```

### 1.5 Trace lookup RPC

```protobuf
rpc GetReasoningTrace(GetReasoningTraceRequest) returns (GetReasoningTraceResponse);
```

`GetReasoningTraceResponse` remains the metadata projection over persisted artifacts.

## 2. Go Runtime Structures

### 2.1 DebateSession

```go
type DebateSession struct {
    DebateID string
    ExecutionID string
    Participants []string
    RoundLimit int
    PerTurnTimeout time.Duration
    CurrentRound int
    Transcript []DebateRound
    Status DebateStatus
    ConsensusReached bool
    ComputeBudget float64
    BudgetUsed float64
    ComputeBudgetExhausted bool
    StorageKey string
}
```

### 2.2 DebateRound and contribution records

```go
type DebateRound struct {
    RoundNumber int
    Contributions []RoundContribution
    ConsensusStatus string
    CompletedAt time.Time
    TerminationCause string
}

type RoundContribution struct {
    AgentFQN string
    StepType string
    Content string
    QualityScore float64
    TokensUsed int64
    MissedTurn bool
    Timestamp time.Time
}
```

### 2.3 ConsolidatedTrace

```go
type ConsolidatedTrace struct {
    ExecutionID string `json:"execution_id"`
    Technique string `json:"technique"`
    SchemaVersion string `json:"schema_version"`
    Status string `json:"status"`
    Steps []TraceStep `json:"steps"`
    TotalTokens int64 `json:"total_tokens"`
    ComputeBudgetUsed float64 `json:"compute_budget_used"`
    EffectiveBudgetScope string `json:"effective_budget_scope,omitempty"`
    ComputeBudgetExhausted bool `json:"compute_budget_exhausted"`
    ConsensusReached bool `json:"consensus_reached,omitempty"`
    Stabilized bool `json:"stabilized,omitempty"`
    DegradationDetected bool `json:"degradation_detected,omitempty"`
    CreatedAt string `json:"created_at,omitempty"`
    LastUpdatedAt string `json:"last_updated_at,omitempty"`
}
```

## 3. Object Storage Keys

| Artifact | Key Pattern |
|---|---|
| Debate consolidated trace | `reasoning-debates/{execution_id}/{debate_id}/trace.json` |
| Self-correction consolidated trace | `reasoning-corrections/{execution_id}/{step_id}/trace.json` |
| React consolidated trace | `reasoning-traces/{execution_id}/{step_id}/react_trace.json` |

## 4. PostgreSQL Metadata Table

`execution_reasoning_trace_records` remains the metadata lookup table and is extended conceptually with `effective_budget_scope`:

```sql
execution_id UUID not null references executions(id)
step_id varchar(255)
technique varchar(50) not null
storage_key varchar(1024) not null
step_count integer
status varchar(20) not null default 'complete'
compute_budget_used double precision
compute_budget_exhausted boolean not null default false
effective_budget_scope varchar(16)
consensus_reached boolean
stabilized boolean
degradation_detected boolean
created_at timestamptz not null default now()
updated_at timestamptz not null default now()
```

## 5. Python API Response Models

```python
class TraceStepResponse(BaseModel):
    step_number: int
    type: str
    agent_fqn: str | None = None
    content: str
    tool_call: dict[str, Any] | None = None
    quality_score: float | None = None
    tokens_used: int | None = None
    timestamp: datetime | None = None

class ReasoningTraceResponse(BaseModel):
    execution_id: UUID
    technique: str
    schema_version: str
    status: str
    steps: list[TraceStepResponse]
    total_tokens: int
    compute_budget_used: float
    effective_budget_scope: str | None = None
    compute_budget_exhausted: bool
    consensus_reached: bool | None = None
    stabilized: bool | None = None
    degradation_detected: bool | None = None
    last_updated_at: datetime | None = None
    pagination: TracePaginationResponse
```
