package reasoningv1

import (
	"context"
	"errors"
	"testing"
	"time"

	"github.com/jackc/pgx/v5"
	"github.com/musematic/reasoning-engine/internal/mode_selector"
	"github.com/musematic/reasoning-engine/pkg/persistence"
	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/status"
)

func traceBoolPtr(value bool) *bool     { return &value }
func float64Ptr(value float64) *float64 { return &value }

type traceStoreStub struct {
	record *persistence.ReasoningTraceRecord
	err    error
	calls  int
}

func (s *traceStoreStub) InsertTraceRecord(context.Context, persistence.ReasoningTraceRecord) error {
	return nil
}

func (s *traceStoreStub) GetTraceRecord(_ context.Context, executionID, stepID string) (*persistence.ReasoningTraceRecord, error) {
	s.calls++
	if s.err != nil {
		return nil, s.err
	}
	if s.record == nil {
		return nil, pgx.ErrNoRows
	}
	return s.record, nil
}

func TestGetReasoningTraceMappings(t *testing.T) {
	now := time.Date(2026, time.April, 19, 12, 0, 0, 0, time.UTC)
	handler := NewHandler(HandlerDependencies{TraceStore: &traceStoreStub{record: &persistence.ReasoningTraceRecord{
		ExecutionID:            "exec-1",
		Technique:              "SELF_CORRECTION",
		Status:                 "in_progress",
		StorageKey:             "reasoning-corrections/exec-1/loop-1/trace.json",
		StepCount:              12,
		ComputeBudgetUsed:      0.7,
		Stabilized:             traceBoolPtr(true),
		DegradationDetected:    traceBoolPtr(false),
		ComputeBudgetExhausted: true,
		EffectiveBudgetScope:   "step",
		UpdatedAt:              now,
	}}})
	resp, err := handler.GetReasoningTrace(context.Background(), &GetReasoningTraceRequest{ExecutionId: "exec-1", StepId: "loop-1"})
	if err != nil {
		t.Fatalf("GetReasoningTrace() error = %v", err)
	}
	if resp.GetTechnique() != "SELF_CORRECTION" || resp.GetStatus() != "in_progress" || resp.GetLastUpdatedAt() == "" || !resp.GetStabilized() || !resp.GetComputeBudgetExhausted() || resp.GetEffectiveBudgetScope() != "step" {
		t.Fatalf("response = %+v", resp)
	}
}

func TestGetReasoningTraceErrors(t *testing.T) {
	if _, err := NewHandler(HandlerDependencies{}).GetReasoningTrace(context.Background(), &GetReasoningTraceRequest{}); status.Code(err) != codes.InvalidArgument {
		t.Fatalf("invalid request code = %s", status.Code(err))
	}
	if _, err := NewHandler(HandlerDependencies{}).GetReasoningTrace(context.Background(), &GetReasoningTraceRequest{ExecutionId: "exec"}); status.Code(err) != codes.Unimplemented {
		t.Fatalf("unimplemented code = %s", status.Code(err))
	}
	if _, err := NewHandler(HandlerDependencies{TraceStore: &traceStoreStub{err: pgx.ErrNoRows}}).GetReasoningTrace(context.Background(), &GetReasoningTraceRequest{ExecutionId: "exec"}); status.Code(err) != codes.NotFound {
		t.Fatalf("not found code = %s", status.Code(err))
	}
	if _, err := NewHandler(HandlerDependencies{TraceStore: &traceStoreStub{err: errors.New("boom")}}).GetReasoningTrace(context.Background(), &GetReasoningTraceRequest{ExecutionId: "exec"}); status.Code(err) != codes.Internal {
		t.Fatalf("internal code = %s", status.Code(err))
	}
}

func TestComputeBudgetMappingHelpers(t *testing.T) {
	allocation := mode_selector.BudgetAllocation{Tokens: 100, Rounds: 10, Cost: 1, TimeMS: 1000}
	if got := mapComputeBudgetToAllocation("DIRECT", 0.5, allocation); got.Tokens != 50 || got.Rounds != 10 || got.Cost != 0.5 || got.TimeMS != 500 {
		t.Fatalf("DIRECT scaled allocation = %+v", got)
	}
	if got := mapComputeBudgetToAllocation("SELF_CORRECTION", 0.25, allocation); got.Tokens != 100 || got.Rounds != 3 || got.Cost != 0.25 || got.TimeMS != 250 {
		t.Fatalf("SELF_CORRECTION scaled allocation = %+v", got)
	}
	if got := mapComputeBudgetToAllocation("DEBATE", 0, allocation); got != allocation {
		t.Fatalf("zero compute budget should not change allocation: %+v", got)
	}
	if scaleInt64(10, 0.01) != 1 {
		t.Fatalf("scaleInt64() should clamp to 1")
	}
	if scaleFloat64(2, 0.5) != 1 {
		t.Fatalf("scaleFloat64() = %v, want 1", scaleFloat64(2, 0.5))
	}
}

func TestSelectReasoningModeRejectsOutOfRangeComputeBudget(t *testing.T) {
	handler := NewHandler(HandlerDependencies{
		ModeSelector: modeSelectorStub{selection: mode_selector.Selection{Mode: "DIRECT", RecommendedBudget: mode_selector.BudgetAllocation{Tokens: 100, Rounds: 1, Cost: 0.1, TimeMS: 1000}}},
	})
	if _, err := handler.SelectReasoningMode(context.Background(), &SelectReasoningModeRequest{ExecutionId: "exec", TaskBrief: "brief", ComputeBudget: float64Ptr(-0.1)}); status.Code(err) != codes.InvalidArgument {
		t.Fatalf("negative compute budget code = %s", status.Code(err))
	}
	if _, err := handler.SelectReasoningMode(context.Background(), &SelectReasoningModeRequest{ExecutionId: "exec", TaskBrief: "brief", ComputeBudget: float64Ptr(1.1)}); status.Code(err) != codes.InvalidArgument {
		t.Fatalf("overflow compute budget code = %s", status.Code(err))
	}
}
