package debate

import "github.com/musematic/reasoning-engine/internal/quality_evaluator"

type ConsensusDetector interface {
	Detect(contributions []RoundContribution) (bool, error)
}

type detector struct {
	evaluator quality_evaluator.Evaluator
	epsilon   float64
}

func NewConsensusDetector(evaluator quality_evaluator.Evaluator, epsilon float64) ConsensusDetector {
	if evaluator == nil {
		evaluator = quality_evaluator.StaticEvaluator{}
	}
	if epsilon <= 0 {
		epsilon = 0.05
	}
	return detector{evaluator: evaluator, epsilon: epsilon}
}

func (d detector) Detect(contributions []RoundContribution) (bool, error) {
	synthesis := make([]RoundContribution, 0, len(contributions))
	for _, contribution := range contributions {
		if contribution.StepType != "synthesis" || contribution.MissedTurn || contribution.Content == "" {
			continue
		}
		synthesis = append(synthesis, contribution)
	}
	if len(synthesis) < 2 {
		return false, nil
	}
	minScore := 1.0
	maxScore := 0.0
	for _, contribution := range synthesis {
		score, err := d.evaluator.Score(contribution.Content)
		if err != nil {
			return false, err
		}
		if score < minScore {
			minScore = score
		}
		if score > maxScore {
			maxScore = score
		}
	}
	return maxScore-minScore <= d.epsilon, nil
}
