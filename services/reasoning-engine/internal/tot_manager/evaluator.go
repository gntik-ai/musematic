package tot_manager

import (
	"context"
	"sort"
)

func (m *Manager) EvaluateBranches(_ context.Context, treeID, scoringFn string) (*SelectionResult, error) {
	wg := m.waitGroup(treeID)
	wg.Wait()

	branches := m.snapshot(treeID)
	if len(branches) == 0 {
		return nil, ErrTreeNotFound
	}

	for i := range branches {
		switch scoringFn {
		case "quality_only":
			branches[i].Score = branches[i].QualityScore
		default:
			branches[i].Score = branches[i].QualityScore / float64(branches[i].TokenCost+1)
		}
	}

	sort.Slice(branches, func(i, j int) bool {
		if branches[i].Score != branches[j].Score {
			return branches[i].Score > branches[j].Score
		}
		if branches[i].TokenCost != branches[j].TokenCost {
			return branches[i].TokenCost < branches[j].TokenCost
		}
		return branches[i].CreatedAt.Before(branches[j].CreatedAt)
	})

	result := &SelectionResult{AllBranches: branches}
	for _, branch := range branches {
		m.metrics.RecordToTBranch(context.Background(), branch.Status)
		if branch.Status == "COMPLETED" {
			result.SelectedBranchID = branch.BranchID
			result.SelectedQuality = branch.QualityScore
			result.SelectedTokenCost = branch.TokenCost
			return result, nil
		}
	}

	result.NoViableBranches = true
	if len(branches) > 0 {
		result.BestPartialBranchID = branches[0].BranchID
	}
	return result, nil
}
