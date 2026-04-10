package tot_manager

import (
	"context"
	"errors"
	"strings"
	"sync"
	"time"

	"github.com/musematic/reasoning-engine/internal/budget_tracker"
	"github.com/musematic/reasoning-engine/internal/quality_evaluator"
	"github.com/musematic/reasoning-engine/pkg/metrics"
)

var (
	ErrBranchExists     = errors.New("branch already exists")
	ErrConcurrencyLimit = errors.New("max tot concurrency reached")
	ErrTreeNotFound     = errors.New("tree not found")
)

type BranchHandle struct {
	TreeID    string
	BranchID  string
	Status    string
	CreatedAt time.Time
}

type BranchSummary struct {
	BranchID     string
	Hypothesis   string
	QualityScore float64
	TokenCost    int64
	Status       string
	Score        float64
	CreatedAt    time.Time
}

type SelectionResult struct {
	SelectedBranchID    string
	SelectedQuality     float64
	SelectedTokenCost   int64
	AllBranches         []BranchSummary
	NoViableBranches    bool
	BestPartialBranchID string
}

type ToTManager interface {
	CreateBranch(ctx context.Context, treeID, branchID, hypothesis string, budget budget_tracker.BudgetAllocation) (*BranchHandle, error)
	EvaluateBranches(ctx context.Context, treeID, scoringFn string) (*SelectionResult, error)
}

type Manager struct {
	budgetTracker budget_tracker.BudgetTracker
	evaluator     quality_evaluator.Evaluator
	metrics       *metrics.Metrics
	semaphore     chan struct{}
	mu            sync.RWMutex
	trees         map[string]map[string]*BranchSummary
	waits         map[string]*sync.WaitGroup
	now           func() time.Time
}

func NewManager(tracker budget_tracker.BudgetTracker, evaluator quality_evaluator.Evaluator, telemetry *metrics.Metrics, maxConcurrency int) *Manager {
	if maxConcurrency <= 0 {
		maxConcurrency = 10
	}
	if evaluator == nil {
		evaluator = quality_evaluator.StaticEvaluator{}
	}
	return &Manager{
		budgetTracker: tracker,
		evaluator:     evaluator,
		metrics:       telemetry,
		semaphore:     make(chan struct{}, maxConcurrency),
		trees:         map[string]map[string]*BranchSummary{},
		waits:         map[string]*sync.WaitGroup{},
		now:           func() time.Time { return time.Now().UTC() },
	}
}

func (m *Manager) waitGroup(treeID string) *sync.WaitGroup {
	m.mu.Lock()
	defer m.mu.Unlock()
	if _, ok := m.waits[treeID]; !ok {
		m.waits[treeID] = &sync.WaitGroup{}
	}
	return m.waits[treeID]
}

func (m *Manager) ensureTreeLocked(treeID string) map[string]*BranchSummary {
	if _, ok := m.trees[treeID]; !ok {
		m.trees[treeID] = map[string]*BranchSummary{}
	}
	return m.trees[treeID]
}

func (m *Manager) createBranchRecord(treeID, branchID, hypothesis string, createdAt time.Time) error {
	m.mu.Lock()
	defer m.mu.Unlock()
	tree := m.ensureTreeLocked(treeID)
	if _, exists := tree[branchID]; exists {
		return ErrBranchExists
	}
	tree[branchID] = &BranchSummary{
		BranchID:   branchID,
		Hypothesis: hypothesis,
		Status:     "CREATED",
		CreatedAt:  createdAt,
	}
	if _, ok := m.waits[treeID]; !ok {
		m.waits[treeID] = &sync.WaitGroup{}
	}
	return nil
}

func (m *Manager) snapshot(treeID string) []BranchSummary {
	m.mu.RLock()
	defer m.mu.RUnlock()
	tree := m.trees[treeID]
	out := make([]BranchSummary, 0, len(tree))
	for _, branch := range tree {
		out = append(out, *branch)
	}
	return out
}

func (m *Manager) updateBranch(treeID, branchID string, update func(branch *BranchSummary)) {
	m.mu.Lock()
	defer m.mu.Unlock()
	if tree, ok := m.trees[treeID]; ok {
		if branch, exists := tree[branchID]; exists {
			update(branch)
		}
	}
}

func (m *Manager) removeBranch(treeID, branchID string) {
	m.mu.Lock()
	defer m.mu.Unlock()
	if tree, ok := m.trees[treeID]; ok {
		delete(tree, branchID)
	}
}

func (m *Manager) hypothesis(treeID, branchID string) string {
	m.mu.RLock()
	defer m.mu.RUnlock()
	if tree, ok := m.trees[treeID]; ok {
		if branch, exists := tree[branchID]; exists {
			return branch.Hypothesis
		}
	}
	return ""
}

func tokenCostFor(hypothesis string) int64 {
	words := len(strings.Fields(strings.TrimSpace(hypothesis)))
	if words < 4 {
		return 2
	}
	return int64(words/4 + 1)
}
