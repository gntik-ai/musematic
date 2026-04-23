package mode_selector

import (
	"context"
	"fmt"
	"strings"
)

var ErrNoModeFits = fmt.Errorf("no mode fits within budget constraints")

type BudgetConstraints struct {
	MaxTokens int64
	MaxRounds int64
	MaxCost   float64
	MaxTimeMS int64
}

type BudgetAllocation struct {
	Tokens int64
	Rounds int64
	Cost   float64
	TimeMS int64
}

type Request struct {
	TaskBrief  string
	ForcedMode string
	Budget     BudgetConstraints
}

type Selection struct {
	Mode              string
	ComplexityScore   int
	RecommendedBudget BudgetAllocation
	Rationale         string
}

type ModeSelector interface {
	Select(context.Context, Request) (Selection, error)
}

type RuleBasedSelector struct {
	modeCosts map[string]BudgetAllocation
}

func NewRuleBasedSelector() *RuleBasedSelector {
	return &RuleBasedSelector{
		modeCosts: map[string]BudgetAllocation{
			"DIRECT":            {Tokens: 500, Rounds: 1, Cost: 0.01, TimeMS: 500},
			"CHAIN_OF_THOUGHT":  {Tokens: 2000, Rounds: 4, Cost: 0.05, TimeMS: 2_000},
			"TREE_OF_THOUGHT":   {Tokens: 5000, Rounds: 8, Cost: 0.10, TimeMS: 5_000},
			"REACT":             {Tokens: 3000, Rounds: 6, Cost: 0.07, TimeMS: 3_000},
			"CODE_AS_REASONING": {Tokens: 2500, Rounds: 5, Cost: 0.06, TimeMS: 3_000},
			"DEBATE":            {Tokens: 4000, Rounds: 6, Cost: 0.08, TimeMS: 4_000},
			"SELF_CORRECTION":   {Tokens: 3000, Rounds: 5, Cost: 0.06, TimeMS: 3_000},
		},
	}
}

func (s *RuleBasedSelector) Select(_ context.Context, req Request) (Selection, error) {
	if forced := strings.TrimSpace(strings.ToUpper(req.ForcedMode)); forced != "" {
		return Selection{
			Mode:              forced,
			ComplexityScore:   Score(req.TaskBrief),
			RecommendedBudget: s.recommendedBudget(forced, req.Budget),
			Rationale:         "forced mode override",
		}, nil
	}

	special := DetectSpecialMode(req.TaskBrief)
	feasible := s.feasibleModes(req.Budget)
	score := Score(req.TaskBrief)
	mode := modeFromScore(score)

	if special != "" && contains(feasible, special) {
		mode = special
	} else if !contains(feasible, mode) {
		mode = s.bestFallback(mode, feasible)
	}

	if mode == "" {
		return Selection{}, ErrNoModeFits
	}

	return Selection{
		Mode:              mode,
		ComplexityScore:   score,
		RecommendedBudget: s.recommendedBudget(mode, req.Budget),
		Rationale:         rationale(mode, score, special, len(feasible)),
	}, nil
}

func (s *RuleBasedSelector) feasibleModes(budget BudgetConstraints) []string {
	out := make([]string, 0, len(s.modeCosts))
	for mode, cost := range s.modeCosts {
		if fitsBudget(cost, budget) {
			out = append(out, mode)
		}
	}
	return out
}

func (s *RuleBasedSelector) bestFallback(preferred string, feasible []string) string {
	order := []string{
		preferred,
		"DEBATE",
		"SELF_CORRECTION",
		"CODE_AS_REASONING",
		"TREE_OF_THOUGHT",
		"CHAIN_OF_THOUGHT",
		"REACT",
		"DIRECT",
	}
	for _, candidate := range order {
		if contains(feasible, candidate) {
			return candidate
		}
	}
	return ""
}

func (s *RuleBasedSelector) recommendedBudget(mode string, budget BudgetConstraints) BudgetAllocation {
	base := s.modeCosts[mode]
	multiplier := map[string]float64{
		"DIRECT":            0.25,
		"CHAIN_OF_THOUGHT":  0.5,
		"TREE_OF_THOUGHT":   0.8,
		"REACT":             0.6,
		"CODE_AS_REASONING": 0.65,
		"DEBATE":            0.7,
		"SELF_CORRECTION":   0.65,
	}[mode]

	if multiplier == 0 {
		multiplier = 0.5
	}

	return BudgetAllocation{
		Tokens: chooseInt64(budget.MaxTokens, base.Tokens, multiplier),
		Rounds: chooseInt64(budget.MaxRounds, base.Rounds, multiplier),
		Cost:   chooseFloat64(budget.MaxCost, base.Cost, multiplier),
		TimeMS: chooseInt64(budget.MaxTimeMS, base.TimeMS, multiplier),
	}
}

func modeFromScore(score int) string {
	switch {
	case score <= 2:
		return "DIRECT"
	case score <= 5:
		return "CHAIN_OF_THOUGHT"
	default:
		return "TREE_OF_THOUGHT"
	}
}

func fitsBudget(cost BudgetAllocation, budget BudgetConstraints) bool {
	if budget.MaxTokens > 0 && cost.Tokens > budget.MaxTokens {
		return false
	}
	if budget.MaxRounds > 0 && cost.Rounds > budget.MaxRounds {
		return false
	}
	if budget.MaxCost > 0 && cost.Cost > budget.MaxCost {
		return false
	}
	if budget.MaxTimeMS > 0 && cost.TimeMS > budget.MaxTimeMS {
		return false
	}
	return true
}

func rationale(mode string, score int, special string, feasibleCount int) string {
	if special != "" && mode == special {
		return fmt.Sprintf("selected %s from keyword override with complexity score %d", mode, score)
	}
	if feasibleCount == 1 {
		return fmt.Sprintf("selected only feasible mode %s", mode)
	}
	return fmt.Sprintf("selected %s from complexity score %d", mode, score)
}

func contains(items []string, target string) bool {
	for _, item := range items {
		if item == target {
			return true
		}
	}
	return false
}

func chooseInt64(limit, fallback int64, multiplier float64) int64 {
	if limit <= 0 {
		return fallback
	}
	value := int64(float64(limit) * multiplier)
	if value <= 0 {
		return 1
	}
	return value
}

func chooseFloat64(limit, fallback, multiplier float64) float64 {
	if limit <= 0 {
		return fallback
	}
	value := limit * multiplier
	if value <= 0 {
		return fallback
	}
	return value
}
