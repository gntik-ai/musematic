package quality_evaluator

import (
	"math"
	"strings"
)

type Evaluator interface {
	Score(hypothesis string) (float64, error)
}

type StaticEvaluator struct{}

func (StaticEvaluator) Score(hypothesis string) (float64, error) {
	words := len(strings.Fields(strings.TrimSpace(hypothesis)))
	if words == 0 {
		return 0, nil
	}
	return math.Min(1, float64(words)/10), nil
}
