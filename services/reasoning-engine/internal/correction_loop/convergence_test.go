package correction_loop

import (
	"context"
	"testing"

	"github.com/google/uuid"
	"github.com/musematic/reasoning-engine/internal/escalation"
)

type recordingProducer struct {
	topics []string
}

func (p *recordingProducer) Produce(_ context.Context, topic, _ string, _ []byte) error {
	p.topics = append(p.topics, topic)
	return nil
}

func TestLoopServiceConvergesAtIterationSix(t *testing.T) {
	producer := &recordingProducer{}
	service := NewLoopService(nil, nil, producer, escalation.NewRouter(producer), nil)
	if _, err := service.Start(context.Background(), "loop-1", "exec-1", LoopConfig{
		MaxIterations: 10,
		CostCap:       5,
		Epsilon:       0.01,
	}); err != nil {
		t.Fatalf("Start() error = %v", err)
	}

	scores := []float64{0.5, 0.7, 0.78, 0.80, 0.805, 0.808}
	var (
		statusValue Status
		iteration   int
		err         error
	)
	for _, score := range scores {
		statusValue, iteration, _, err = service.Submit(context.Background(), "loop-1", score, 0.1, 500)
		if err != nil {
			t.Fatalf("Submit() error = %v", err)
		}
	}
	if statusValue != StatusConverged || iteration != 6 {
		t.Fatalf("status = %s iteration = %d, want %s/6", statusValue, iteration, StatusConverged)
	}
}

func TestLoopServiceBudgetExceededAndEscalation(t *testing.T) {
	producer := &recordingProducer{}
	service := NewLoopService(nil, nil, producer, escalation.NewRouter(producer), nil)
	if _, err := service.Start(context.Background(), "loop-2", "exec-2", LoopConfig{
		MaxIterations:            3,
		CostCap:                  100,
		Epsilon:                  0.0001,
		EscalateOnBudgetExceeded: true,
	}); err != nil {
		t.Fatalf("Start() error = %v", err)
	}

	statusValue := StatusContinue
	for _, score := range []float64{0.5, 0.7, 0.9} {
		var err error
		statusValue, _, _, err = service.Submit(context.Background(), "loop-2", score, 0.1, 100)
		if err != nil {
			t.Fatalf("Submit() error = %v", err)
		}
	}

	if statusValue != StatusEscalateToHuman {
		t.Fatalf("status = %s, want %s", statusValue, StatusEscalateToHuman)
	}
	if len(producer.topics) < 2 {
		t.Fatalf("expected runtime and escalation events, got %+v", producer.topics)
	}
}

func TestLoopServiceCostCapAndDisabledConvergence(t *testing.T) {
	service := NewLoopService(nil, nil, nil, nil, nil)
	if _, err := service.Start(context.Background(), "loop-3", "exec-3", LoopConfig{
		MaxIterations: 5,
		CostCap:       0.2,
		Epsilon:       0,
	}); err != nil {
		t.Fatalf("Start() error = %v", err)
	}

	statusValue, _, _, err := service.Submit(context.Background(), "loop-3", 0.5, 0.1, 100)
	if err != nil {
		t.Fatalf("Submit() error = %v", err)
	}
	if statusValue != StatusContinue {
		t.Fatalf("status = %s, want %s", statusValue, StatusContinue)
	}

	statusValue, _, _, err = service.Submit(context.Background(), "loop-3", 0.51, 0.11, 100)
	if err != nil {
		t.Fatalf("Submit() error = %v", err)
	}
	if statusValue != StatusBudgetExceeded {
		t.Fatalf("status = %s, want %s", statusValue, StatusBudgetExceeded)
	}
}

func TestLoopServiceValidationAndStateErrors(t *testing.T) {
	service := NewLoopService(nil, nil, nil, nil, nil)
	if _, err := service.Start(context.Background(), "loop-4", "exec-4", LoopConfig{}); err == nil {
		t.Fatal("expected invalid config error")
	}
	if _, err := service.Start(context.Background(), "loop-5", "exec-5", LoopConfig{MaxIterations: 2, CostCap: 1, Epsilon: 0.1}); err != nil {
		t.Fatalf("Start() error = %v", err)
	}
	if _, err := service.Start(context.Background(), "loop-5", "exec-5", LoopConfig{MaxIterations: 2, CostCap: 1, Epsilon: 0.1}); err != ErrLoopExists {
		t.Fatalf("duplicate start error = %v, want %v", err, ErrLoopExists)
	}
	if _, _, _, err := service.Submit(context.Background(), "missing", 0.5, 0.1, 10); err != ErrLoopNotFound {
		t.Fatalf("missing loop error = %v, want %v", err, ErrLoopNotFound)
	}
	if _, _, _, err := service.Submit(context.Background(), "loop-5", 2, 0.1, 10); err == nil {
		t.Fatal("expected invalid quality error")
	}
	if _, _, _, err := service.Submit(context.Background(), "loop-5", 0.2, 0.1, 10); err != nil {
		t.Fatalf("Submit() error = %v", err)
	}
	if _, _, _, err := service.Submit(context.Background(), "loop-5", 0.4, 0.1, 10); err != nil {
		t.Fatalf("Submit() error = %v", err)
	}
	if _, _, _, err := service.Submit(context.Background(), "loop-5", 0.4, 0.1, 10); err == nil {
		t.Fatal("expected loop-not-running error after convergence/budget update path")
	}
}

func TestLoopHelpers(t *testing.T) {
	service := NewLoopService(nil, nil, nil, nil, nil)
	if err := service.publishRuntimeEvent(context.Background(), "type", loopState{ExecutionID: "exec"}, 0.5); err != nil {
		t.Fatalf("publishRuntimeEvent() error = %v", err)
	}
	if err := service.persistIteration(context.Background(), loopState{LoopID: "loop", UsedIterations: 1}, 0.5, 0, 0.1, 10); err != nil {
		t.Fatalf("persistIteration() error = %v", err)
	}
	if redisKey("loop") != "correction:loop" {
		t.Fatalf("redisKey() returned %s", redisKey("loop"))
	}
	if parseEvalInt("3") != 3 || parseEvalFloat("1.5") != 1.5 {
		t.Fatal("parseEval helpers did not parse strings")
	}
	if nullableDelta(1, 0.1) != nil {
		t.Fatal("nullableDelta() should return nil on first iteration")
	}
	if uuidFor("loop") == uuid.Nil {
		t.Fatal("uuidFor() should create deterministic uuid")
	}
}
