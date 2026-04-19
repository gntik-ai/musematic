package reasoningv1

import (
	"context"
	"testing"

	"github.com/musematic/reasoning-engine/internal/correction_loop"
	"github.com/musematic/reasoning-engine/internal/debate"
	"github.com/musematic/reasoning-engine/internal/mode_selector"
	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/status"
)

func TestSelectReasoningModeAcceptsOmittedComputeBudgetAndRejectsExplicitInvalidValues(t *testing.T) {
	handler := NewHandler(HandlerDependencies{
		ModeSelector: modeSelectorStub{selection: mode_selector.Selection{
			Mode:              "DIRECT",
			ComplexityScore:   2,
			RecommendedBudget: mode_selector.BudgetAllocation{Tokens: 100, Rounds: 4, Cost: 0.4, TimeMS: 800},
			Rationale:         "simple",
		}},
	})

	resp, err := handler.SelectReasoningMode(context.Background(), &SelectReasoningModeRequest{
		ExecutionId: "exec-budget",
		TaskBrief:   "brief",
	})
	if err != nil {
		t.Fatalf("SelectReasoningMode(omitted) error = %v", err)
	}
	if resp.GetRecommendedBudget().GetTokens() != 100 {
		t.Fatalf("unexpected omitted-budget allocation: %+v", resp.GetRecommendedBudget())
	}

	scaled, err := handler.SelectReasoningMode(context.Background(), &SelectReasoningModeRequest{
		ExecutionId:   "exec-budget",
		TaskBrief:     "brief",
		ComputeBudget: float64Ptr(0.5),
	})
	if err != nil {
		t.Fatalf("SelectReasoningMode(valid) error = %v", err)
	}
	if scaled.GetRecommendedBudget().GetTokens() != 50 || scaled.GetRecommendedBudget().GetTimeMs() != 400 {
		t.Fatalf("unexpected scaled allocation: %+v", scaled.GetRecommendedBudget())
	}

	if _, err := handler.SelectReasoningMode(context.Background(), &SelectReasoningModeRequest{ExecutionId: "exec-budget", TaskBrief: "brief", ComputeBudget: float64Ptr(0)}); status.Code(err) != codes.InvalidArgument {
		t.Fatalf("zero compute budget code = %s", status.Code(err))
	}
	if _, err := handler.SelectReasoningMode(context.Background(), &SelectReasoningModeRequest{ExecutionId: "exec-budget", TaskBrief: "brief", ComputeBudget: float64Ptr(1.1)}); status.Code(err) != codes.InvalidArgument {
		t.Fatalf("overflow compute budget code = %s", status.Code(err))
	}
}

func TestReasoningHandlersRejectInvalidBudgetsAndEnforceSelfCorrectionBudget(t *testing.T) {
	uploader := &capturingTraceUploader{}
	traceStore := &capturingTraceStore{}
	handler := NewHandler(HandlerDependencies{
		DebateService:  debate.NewService(debate.NewConsensusDetector(nil, 0.05), &capturingTraceUploader{}, &capturingTraceStore{}, &capturingReasoningEvents{}),
		CorrectionLoop: &scriptedCorrectionLoop{submits: []correctionLoopResult{{status: correction_loop.StatusContinue, iteration: 2, delta: 0.05}}},
		TraceUploader:  uploader,
		TraceStore:     traceStore,
	})

	if _, err := handler.StartDebateSession(context.Background(), &StartDebateSessionRequest{
		ExecutionId:     "exec-budget-debate",
		DebateId:        "debate-budget",
		ParticipantFqns: []string{"agent.alpha", "agent.beta"},
		RoundLimit:      2,
		ComputeBudget:   float64Ptr(0),
	}); status.Code(err) != codes.InvalidArgument {
		t.Fatalf("debate zero compute budget code = %s", status.Code(err))
	}
	if _, err := handler.StartSelfCorrectionLoop(context.Background(), &StartSelfCorrectionRequest{
		LoopId:        "loop-invalid",
		ExecutionId:   "exec-invalid",
		MaxIterations: 4,
		CostCap:       1,
		Epsilon:       0.01,
		ComputeBudget: float64Ptr(0),
	}); status.Code(err) != codes.InvalidArgument {
		t.Fatalf("self-correction zero compute budget code = %s", status.Code(err))
	}

	if _, err := handler.StartSelfCorrectionLoop(context.Background(), &StartSelfCorrectionRequest{
		LoopId:               "loop-budget",
		ExecutionId:          "exec-budget",
		StepId:               "step-budget",
		MaxIterations:        4,
		CostCap:              2,
		Epsilon:              0.01,
		ComputeBudget:        float64Ptr(0.5),
		DegradationThreshold: 0.2,
	}); err != nil {
		t.Fatalf("StartSelfCorrectionLoop(valid) error = %v", err)
	}
	result, err := handler.SubmitCorrectionIteration(context.Background(), &CorrectionIterationEvent{
		LoopId:        "loop-budget",
		IterationNum:  2,
		QualityScore:  0.8,
		Cost:          0.3,
		DurationMs:    40,
		PriorAnswer:   "draft",
		Critique:      "improve",
		RefinedAnswer: "better",
	})
	if err != nil {
		t.Fatalf("SubmitCorrectionIteration() error = %v", err)
	}
	if result.GetStatus() != ConvergenceStatus_BUDGET_EXCEEDED {
		t.Fatalf("status = %v, want %v", result.GetStatus(), ConvergenceStatus_BUDGET_EXCEEDED)
	}
	if len(traceStore.records) != 1 || !traceStore.records[0].ComputeBudgetExhausted {
		t.Fatalf("trace records = %+v", traceStore.records)
	}
	if len(uploader.uploads) != 1 || !uploader.uploads[0].ComputeBudgetExhausted {
		t.Fatalf("uploaded traces = %+v", uploader.uploads)
	}
}
