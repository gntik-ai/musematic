package reasoningv1

import (
	"context"
	"testing"
	"time"

	"github.com/musematic/reasoning-engine/internal/correction_loop"
)

type correctionLoopResult struct {
	status    correction_loop.Status
	iteration int
	delta     float64
	err       error
}

type scriptedCorrectionLoop struct {
	startErr   error
	startAt    time.Time
	submits    []correctionLoopResult
	submitCall int
}

func (s *scriptedCorrectionLoop) Start(_ context.Context, loopID, execID string, _ correction_loop.LoopConfig) (*correction_loop.LoopHandle, error) {
	if s.startErr != nil {
		return nil, s.startErr
	}
	startedAt := s.startAt
	if startedAt.IsZero() {
		startedAt = time.Now().UTC()
	}
	return &correction_loop.LoopHandle{LoopID: loopID, ExecutionID: execID, Status: "RUNNING", StartedAt: startedAt}, nil
}

func (s *scriptedCorrectionLoop) Submit(context.Context, string, float64, float64, int64) (correction_loop.Status, int, float64, error) {
	if s.submitCall >= len(s.submits) {
		return correction_loop.StatusContinue, s.submitCall + 1, 0, nil
	}
	result := s.submits[s.submitCall]
	s.submitCall++
	return result.status, result.iteration, result.delta, result.err
}

func TestSelfCorrectionRPCsPersistTraceOnStabilization(t *testing.T) {
	loop := &scriptedCorrectionLoop{submits: []correctionLoopResult{{status: correction_loop.StatusConverged, iteration: 2, delta: 0.01}}}
	uploader := &capturingTraceUploader{}
	traceStore := &capturingTraceStore{}
	handler := NewHandler(HandlerDependencies{CorrectionLoop: loop, TraceUploader: uploader, TraceStore: traceStore})

	if _, err := handler.StartSelfCorrectionLoop(context.Background(), &StartSelfCorrectionRequest{
		LoopId:               "loop-stable",
		ExecutionId:          "exec-stable",
		StepId:               "step-stable",
		MaxIterations:        4,
		CostCap:              2,
		Epsilon:              0.01,
		ComputeBudget:        float64Ptr(0.8),
		DegradationThreshold: 0.2,
	}); err != nil {
		t.Fatalf("StartSelfCorrectionLoop() error = %v", err)
	}

	result, err := handler.SubmitCorrectionIteration(context.Background(), &CorrectionIterationEvent{
		LoopId:        "loop-stable",
		IterationNum:  2,
		QualityScore:  0.92,
		Cost:          0.2,
		DurationMs:    50,
		PriorAnswer:   "draft answer",
		Critique:      "tighten evidence",
		RefinedAnswer: "refined answer",
	})
	if err != nil {
		t.Fatalf("SubmitCorrectionIteration() error = %v", err)
	}
	if result.GetStatus() != ConvergenceStatus_CONVERGED {
		t.Fatalf("status = %v, want %v", result.GetStatus(), ConvergenceStatus_CONVERGED)
	}
	if len(uploader.uploads) != 1 || len(uploader.uploads[0].Steps) != 3 {
		t.Fatalf("uploaded traces = %+v", uploader.uploads)
	}
	trace := uploader.uploads[0]
	if !trace.Stabilized || trace.DegradationDetected {
		t.Fatalf("unexpected trace flags: %+v", trace)
	}
	if trace.Steps[0].Type != "iteration_input" || trace.Steps[1].Content != "tighten evidence" || trace.Steps[2].Content != "refined answer" {
		t.Fatalf("unexpected trace steps: %+v", trace.Steps)
	}
	if len(traceStore.records) != 1 || traceStore.records[0].Stabilized == nil || !*traceStore.records[0].Stabilized {
		t.Fatalf("trace records = %+v", traceStore.records)
	}
}

func TestSelfCorrectionRPCsDetectDegradationAndPersistTriplets(t *testing.T) {
	loop := &scriptedCorrectionLoop{submits: []correctionLoopResult{
		{status: correction_loop.StatusContinue, iteration: 1, delta: 0.4},
		{status: correction_loop.StatusContinue, iteration: 2, delta: 0.6},
	}}
	uploader := &capturingTraceUploader{}
	traceStore := &capturingTraceStore{}
	handler := NewHandler(HandlerDependencies{CorrectionLoop: loop, TraceUploader: uploader, TraceStore: traceStore})

	if _, err := handler.StartSelfCorrectionLoop(context.Background(), &StartSelfCorrectionRequest{
		LoopId:               "loop-degrade",
		ExecutionId:          "exec-degrade",
		MaxIterations:        4,
		CostCap:              2,
		Epsilon:              0.01,
		DegradationThreshold: 0.2,
	}); err != nil {
		t.Fatalf("StartSelfCorrectionLoop() error = %v", err)
	}
	if _, err := handler.SubmitCorrectionIteration(context.Background(), &CorrectionIterationEvent{
		LoopId:        "loop-degrade",
		IterationNum:  1,
		QualityScore:  0.95,
		Cost:          0.1,
		DurationMs:    40,
		PriorAnswer:   "best draft",
		Critique:      "keep detail",
		RefinedAnswer: "best answer",
	}); err != nil {
		t.Fatalf("SubmitCorrectionIteration(first) error = %v", err)
	}
	result, err := handler.SubmitCorrectionIteration(context.Background(), &CorrectionIterationEvent{
		LoopId:        "loop-degrade",
		IterationNum:  2,
		QualityScore:  0.5,
		Cost:          0.2,
		DurationMs:    35,
		PriorAnswer:   "best answer",
		Critique:      "regressed",
		RefinedAnswer: "worse answer",
	})
	if err != nil {
		t.Fatalf("SubmitCorrectionIteration(second) error = %v", err)
	}
	if result.GetStatus() != ConvergenceStatus_CONVERGED {
		t.Fatalf("status = %v, want degraded convergence", result.GetStatus())
	}
	trace := uploader.uploads[0]
	if !trace.DegradationDetected || trace.Stabilized {
		t.Fatalf("unexpected degradation trace: %+v", trace)
	}
	if len(trace.Steps) != 6 || trace.Steps[5].Content != "worse answer" {
		t.Fatalf("unexpected degraded steps: %+v", trace.Steps)
	}
	if traceStore.records[0].DegradationDetected == nil || !*traceStore.records[0].DegradationDetected {
		t.Fatalf("trace record = %+v", traceStore.records[0])
	}
}

func TestSelfCorrectionRPCsPersistTraceWhenLoopHitsMaxIterations(t *testing.T) {
	loop := &scriptedCorrectionLoop{submits: []correctionLoopResult{{status: correction_loop.StatusBudgetExceeded, iteration: 3, delta: 0.2}}}
	uploader := &capturingTraceUploader{}
	traceStore := &capturingTraceStore{}
	handler := NewHandler(HandlerDependencies{CorrectionLoop: loop, TraceUploader: uploader, TraceStore: traceStore})

	if _, err := handler.StartSelfCorrectionLoop(context.Background(), &StartSelfCorrectionRequest{
		LoopId:               "loop-max",
		ExecutionId:          "exec-max",
		StepId:               "step-max",
		MaxIterations:        3,
		CostCap:              3,
		Epsilon:              0.01,
		DegradationThreshold: 0.2,
	}); err != nil {
		t.Fatalf("StartSelfCorrectionLoop() error = %v", err)
	}
	result, err := handler.SubmitCorrectionIteration(context.Background(), &CorrectionIterationEvent{
		LoopId:        "loop-max",
		IterationNum:  3,
		QualityScore:  0.6,
		Cost:          0.9,
		DurationMs:    70,
		PriorAnswer:   "draft",
		Critique:      "still inconclusive",
		RefinedAnswer: "revised draft",
	})
	if err != nil {
		t.Fatalf("SubmitCorrectionIteration() error = %v", err)
	}
	if result.GetStatus() != ConvergenceStatus_BUDGET_EXCEEDED {
		t.Fatalf("status = %v, want %v", result.GetStatus(), ConvergenceStatus_BUDGET_EXCEEDED)
	}
	if len(traceStore.records) != 1 || traceStore.records[0].ComputeBudgetExhausted {
		t.Fatalf("trace records = %+v", traceStore.records)
	}
}
