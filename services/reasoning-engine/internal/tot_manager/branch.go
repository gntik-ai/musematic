package tot_manager

import (
	"context"
	"sync"

	"github.com/musematic/reasoning-engine/internal/budget_tracker"
)

func (m *Manager) CreateBranch(ctx context.Context, treeID, branchID, hypothesis string, budget budget_tracker.BudgetAllocation) (*BranchHandle, error) {
	createdAt := m.now()
	if err := m.createBranchRecord(treeID, branchID, hypothesis, createdAt); err != nil {
		return nil, err
	}

	select {
	case m.semaphore <- struct{}{}:
	default:
		m.removeBranch(treeID, branchID)
		return nil, ErrConcurrencyLimit
	}

	handle := &BranchHandle{
		TreeID:    treeID,
		BranchID:  branchID,
		Status:    "CREATED",
		CreatedAt: createdAt,
	}

	if m.budgetTracker != nil {
		if err := m.budgetTracker.Allocate(ctx, treeID, branchID, budget, 3600); err != nil && err != budget_tracker.ErrAlreadyExists {
			<-m.semaphore
			m.removeBranch(treeID, branchID)
			return nil, err
		}
	}

	wg := m.waitGroup(treeID)
	wg.Add(1)
	go m.runBranch(context.Background(), wg, treeID, branchID)

	return handle, nil
}

func (m *Manager) runBranch(parent context.Context, wg *sync.WaitGroup, treeID, branchID string) {
	defer func() {
		<-m.semaphore
		wg.Done()
	}()

	ctx, cancel := context.WithCancelCause(parent)
	defer cancel(nil)

	m.updateBranch(treeID, branchID, func(branch *BranchSummary) {
		branch.Status = "ACTIVE"
	})

	defer func() {
		if recovered := recover(); recovered != nil {
			m.updateBranch(treeID, branchID, func(branch *BranchSummary) {
				branch.Status = "FAILED"
			})
		}
	}()

	hypothesis := m.hypothesis(treeID, branchID)

	tokenCost := tokenCostFor(hypothesis)
	if m.budgetTracker != nil {
		if _, err := m.budgetTracker.Decrement(ctx, treeID, branchID, "tokens", float64(tokenCost)); err != nil {
			cancel(err)
			m.updateBranch(treeID, branchID, func(branch *BranchSummary) {
				branch.Status = "PRUNED"
				branch.TokenCost = tokenCost
			})
			return
		}
	}

	score, err := m.evaluator.Score(hypothesis)
	if err != nil {
		m.updateBranch(treeID, branchID, func(branch *BranchSummary) {
			branch.Status = "FAILED"
			branch.TokenCost = tokenCost
		})
		return
	}

	m.updateBranch(treeID, branchID, func(branch *BranchSummary) {
		branch.Status = "COMPLETED"
		branch.QualityScore = score
		branch.TokenCost = tokenCost
	})
}
