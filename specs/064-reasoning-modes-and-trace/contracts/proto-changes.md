# Proto Contract: Advanced Reasoning Modes and Trace Export

**Feature**: 064-reasoning-modes-and-trace | **Date**: 2026-04-19  
**File**: `services/reasoning-engine/proto/reasoning_engine.proto`

## Changes to Existing Messages

### ReasoningMode enum

```diff
 enum ReasoningMode {
   REASONING_MODE_UNSPECIFIED = 0;
   DIRECT = 1;
   CHAIN_OF_THOUGHT = 2;
   TREE_OF_THOUGHT = 3;
   REACT = 4;
   CODE_AS_REASONING = 5;
   DEBATE = 6;
+  SELF_CORRECTION = 7;
 }
```

### SelectReasoningModeRequest

```diff
 message SelectReasoningModeRequest {
   string execution_id = 1;
   string task_brief = 2;
   string forced_mode = 3;
   BudgetConstraints budget_constraints = 4;
-  double compute_budget = 7;
+  optional double compute_budget = 7;
 }
```

`optional` is required so the server can distinguish “field omitted” from `0.0`, which the spec treats as invalid when explicitly supplied.

### StartSelfCorrectionRequest

```diff
 message StartSelfCorrectionRequest {
   string loop_id = 1;
   string execution_id = 2;
   int32 max_iterations = 3;
   double cost_cap = 4;
   double epsilon = 5;
   bool escalate_on_budget_exceeded = 6;
+  string step_id = 7;
+  optional double compute_budget = 8;
+  double degradation_threshold = 9;
 }
```

### CorrectionIterationEvent

```diff
 message CorrectionIterationEvent {
   string loop_id = 1;
   double quality_score = 2;
   double cost = 3;
   int64 duration_ms = 4;
+  string prior_answer = 5;
+  string critique = 6;
+  string refined_answer = 7;
+  int32 iteration_num = 8;
 }
```

## New Debate RPCs

```protobuf
service ReasoningEngineService {
  // existing RPCs omitted for brevity
  rpc StartDebateSession(StartDebateSessionRequest) returns (DebateSessionHandle);
  rpc SubmitDebateTurn(SubmitDebateTurnRequest) returns (DebateRoundResult);
  rpc FinalizeDebateSession(FinalizeDebateSessionRequest) returns (DebateSessionResult);
}
```

```protobuf
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
  string step_type = 3;
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

## Existing Trace Lookup RPC

`GetReasoningTrace` remains unchanged from the current additive slice and keeps returning metadata plus storage-key lookup information.

## Budget Scope Resolution

Workflow-vs-step precedence is intentionally **not** added to gRPC. The control plane computes the effective budget and passes a single normalized `compute_budget` value to Go.

## Regeneration Command

```bash
cd services/reasoning-engine
buf generate proto/reasoning_engine.proto
```
