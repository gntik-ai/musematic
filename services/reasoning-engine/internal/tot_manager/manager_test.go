package tot_manager

import (
	"context"
	"errors"
	"strconv"
	"sync"
	"testing"
	"time"

	"github.com/musematic/reasoning-engine/internal/budget_tracker"
	"github.com/musematic/reasoning-engine/internal/quality_evaluator"
)

type fakeBudgetTracker struct {
	mu     sync.Mutex
	limits map[string]float64
	used   map[string]float64
}

func newFakeBudgetTracker() *fakeBudgetTracker {
	return &fakeBudgetTracker{
		limits: map[string]float64{},
		used:   map[string]float64{},
	}
}

func (t *fakeBudgetTracker) Allocate(_ context.Context, execID, stepID string, limits budget_tracker.BudgetAllocation, _ int64) error {
	t.mu.Lock()
	defer t.mu.Unlock()
	key := budget_tracker.Key(execID, stepID)
	t.limits[key] = float64(limits.Tokens)
	return nil
}

func (t *fakeBudgetTracker) Decrement(_ context.Context, execID, stepID, _ string, amount float64) (float64, error) {
	t.mu.Lock()
	defer t.mu.Unlock()
	key := budget_tracker.Key(execID, stepID)
	if t.used[key]+amount > t.limits[key] {
		return 0, budget_tracker.ErrBudgetExceeded
	}
	t.used[key] += amount
	return t.used[key], nil
}

func (t *fakeBudgetTracker) GetStatus(_ context.Context, execID, stepID string) (*budget_tracker.BudgetStatus, error) {
	t.mu.Lock()
	defer t.mu.Unlock()
	key := budget_tracker.Key(execID, stepID)
	return &budget_tracker.BudgetStatus{
		ExecutionID: execID,
		StepID:      stepID,
		Limits:      budget_tracker.BudgetAllocation{Tokens: int64(t.limits[key])},
		Used:        budget_tracker.BudgetAllocation{Tokens: int64(t.used[key])},
	}, nil
}

type scoringEvaluator struct {
	scores  map[string]float64
	errOn   string
	panicOn string
	block   chan struct{}
}

func (e scoringEvaluator) Score(hypothesis string) (float64, error) {
	if e.block != nil {
		<-e.block
	}
	if hypothesis == e.panicOn {
		panic("boom")
	}
	if hypothesis == e.errOn {
		return 0, errors.New("score failed")
	}
	if score, ok := e.scores[hypothesis]; ok {
		return score, nil
	}
	return quality_evaluator.StaticEvaluator{}.Score(hypothesis)
}

func TestManagerSelectsBestCompletedBranch(t *testing.T) {
	tracker := newFakeBudgetTracker()
	manager := NewManager(tracker, scoringEvaluator{scores: map[string]float64{
		"alpha hypothesis words": 0.8,
		"beta hypothesis words":  0.9,
		"gamma hypothesis words": 0.7,
	}}, nil, 10)

	branches := []string{"alpha hypothesis words", "beta hypothesis words", "gamma hypothesis words"}
	for i, hypothesis := range branches {
		if _, err := manager.CreateBranch(context.Background(), "tree-1", "branch-"+strconv.Itoa(i), hypothesis, budget_tracker.BudgetAllocation{Tokens: 10}); err != nil {
			t.Fatalf("CreateBranch() error = %v", err)
		}
	}

	result, err := manager.EvaluateBranches(context.Background(), "tree-1", "quality_only")
	if err != nil {
		t.Fatalf("EvaluateBranches() error = %v", err)
	}
	if result.SelectedBranchID == "" {
		t.Fatal("expected selected branch")
	}
	if result.SelectedQuality != 0.9 {
		t.Fatalf("selected quality = %v, want 0.9", result.SelectedQuality)
	}
}

func TestManagerPrunesBudgetExceededBranch(t *testing.T) {
	tracker := newFakeBudgetTracker()
	manager := NewManager(tracker, scoringEvaluator{}, nil, 10)

	if _, err := manager.CreateBranch(context.Background(), "tree-2", "branch-1", "tiny", budget_tracker.BudgetAllocation{Tokens: 1}); err != nil {
		t.Fatalf("CreateBranch() error = %v", err)
	}

	result, err := manager.EvaluateBranches(context.Background(), "tree-2", "quality_cost_ratio")
	if err != nil {
		t.Fatalf("EvaluateBranches() error = %v", err)
	}
	if !result.NoViableBranches {
		t.Fatalf("expected no viable branches, got %+v", result)
	}
	if result.BestPartialBranchID != "branch-1" {
		t.Fatalf("best partial branch = %s, want branch-1", result.BestPartialBranchID)
	}
}

func TestManagerHandlesConcurrencyLimitAndPanicRecovery(t *testing.T) {
	tracker := newFakeBudgetTracker()
	block := make(chan struct{})
	manager := NewManager(tracker, scoringEvaluator{panicOn: "panic branch", block: block}, nil, 1)

	if _, err := manager.CreateBranch(context.Background(), "tree-3", "branch-1", "panic branch", budget_tracker.BudgetAllocation{Tokens: 10}); err != nil {
		t.Fatalf("CreateBranch() error = %v", err)
	}
	if _, err := manager.CreateBranch(context.Background(), "tree-3", "branch-2", "second branch words", budget_tracker.BudgetAllocation{Tokens: 10}); !errors.Is(err, ErrConcurrencyLimit) {
		t.Fatalf("CreateBranch() error = %v, want %v", err, ErrConcurrencyLimit)
	}
	close(block)

	result, err := manager.EvaluateBranches(context.Background(), "tree-3", "quality_cost_ratio")
	if err != nil {
		t.Fatalf("EvaluateBranches() error = %v", err)
	}
	if !result.NoViableBranches {
		t.Fatalf("expected no viable branches after panic, got %+v", result)
	}
}

func TestManagerDuplicateBranchAndTreeNotFound(t *testing.T) {
	tracker := newFakeBudgetTracker()
	manager := NewManager(tracker, scoringEvaluator{errOn: "error branch"}, nil, 10)

	if _, err := manager.CreateBranch(context.Background(), "tree-4", "branch-1", "error branch", budget_tracker.BudgetAllocation{Tokens: 10}); err != nil {
		t.Fatalf("CreateBranch() error = %v", err)
	}
	if _, err := manager.CreateBranch(context.Background(), "tree-4", "branch-1", "duplicate", budget_tracker.BudgetAllocation{Tokens: 10}); !errors.Is(err, ErrBranchExists) {
		t.Fatalf("duplicate CreateBranch() error = %v", err)
	}
	if _, err := manager.EvaluateBranches(context.Background(), "missing-tree", "quality_only"); !errors.Is(err, ErrTreeNotFound) {
		t.Fatalf("EvaluateBranches() error = %v, want %v", err, ErrTreeNotFound)
	}
	result, err := manager.EvaluateBranches(context.Background(), "tree-4", "quality_only")
	if err != nil {
		t.Fatalf("EvaluateBranches() error = %v", err)
	}
	if !result.NoViableBranches {
		t.Fatalf("expected no viable branches for evaluator error, got %+v", result)
	}
}

func TestManagerHelpers(t *testing.T) {
	manager := NewManager(nil, nil, nil, 0)
	if cap(manager.semaphore) != 10 {
		t.Fatalf("default concurrency = %d, want 10", cap(manager.semaphore))
	}

	createdAt := time.Unix(10, 0).UTC()
	if err := manager.createBranchRecord("tree-helpers", "branch-1", "helper hypothesis", createdAt); err != nil {
		t.Fatalf("createBranchRecord() error = %v", err)
	}
	if err := manager.createBranchRecord("tree-helpers", "branch-1", "duplicate", createdAt); !errors.Is(err, ErrBranchExists) {
		t.Fatalf("duplicate createBranchRecord() error = %v", err)
	}

	firstWG := manager.waitGroup("tree-helpers")
	secondWG := manager.waitGroup("tree-helpers")
	if firstWG != secondWG {
		t.Fatal("waitGroup() should reuse the same wait group per tree")
	}

	snapshot := manager.snapshot("tree-helpers")
	if len(snapshot) != 1 || snapshot[0].BranchID != "branch-1" {
		t.Fatalf("snapshot() = %+v", snapshot)
	}

	manager.updateBranch("tree-helpers", "branch-1", func(branch *BranchSummary) {
		branch.Status = "COMPLETED"
		branch.Score = 0.9
	})
	if got := manager.hypothesis("tree-helpers", "branch-1"); got != "helper hypothesis" {
		t.Fatalf("hypothesis() = %q", got)
	}

	manager.removeBranch("tree-helpers", "branch-1")
	if got := manager.hypothesis("tree-helpers", "branch-1"); got != "" {
		t.Fatalf("hypothesis() after remove = %q", got)
	}

	if got := tokenCostFor("tiny words"); got != 2 {
		t.Fatalf("tokenCostFor(short) = %d, want 2", got)
	}
	if got := tokenCostFor("one two three four five six seven eight"); got != 3 {
		t.Fatalf("tokenCostFor(long) = %d, want 3", got)
	}
}
