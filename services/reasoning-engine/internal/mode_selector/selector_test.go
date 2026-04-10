package mode_selector

import (
	"context"
	"testing"
)

func TestRuleBasedSelectorSelectsExpectedModes(t *testing.T) {
	selector := NewRuleBasedSelector()

	tests := []struct {
		name    string
		request Request
		want    string
	}{
		{
			name: "simple task uses direct",
			request: Request{
				TaskBrief: "What is 2+2?",
				Budget:    BudgetConstraints{MaxTokens: 1000},
			},
			want: "DIRECT",
		},
		{
			name: "multi-step task uses chain of thought",
			request: Request{
				TaskBrief: "First gather the inputs, then compare the options, and finally pick the safest rollout.",
				Budget:    BudgetConstraints{MaxTokens: 5000, MaxRounds: 10},
			},
			want: "CHAIN_OF_THOUGHT",
		},
		{
			name: "complex long task uses tree of thought",
			request: Request{
				TaskBrief: "First analyse the requirements, then decompose the migration plan into phases, then identify integration risks, then model rollback options, then compare tradeoffs, and finally write a staged deployment checklist with decision points and open questions for each environment.",
				Budget:    BudgetConstraints{MaxTokens: 12000, MaxRounds: 20, MaxCost: 1, MaxTimeMS: 10000},
			},
			want: "TREE_OF_THOUGHT",
		},
		{
			name: "forced mode overrides heuristics",
			request: Request{
				TaskBrief:  "What is 2+2?",
				ForcedMode: "tree_of_thought",
				Budget:     BudgetConstraints{MaxTokens: 100},
			},
			want: "TREE_OF_THOUGHT",
		},
		{
			name: "code keywords route to code as reasoning",
			request: Request{
				TaskBrief: "Write a Python function and explain the script.",
				Budget:    BudgetConstraints{MaxTokens: 5000, MaxRounds: 10},
			},
			want: "CODE_AS_REASONING",
		},
		{
			name: "debate keywords route to debate",
			request: Request{
				TaskBrief: "Compare the two architectures and debate the pros and cons.",
				Budget:    BudgetConstraints{MaxTokens: 5000, MaxRounds: 10},
			},
			want: "DEBATE",
		},
		{
			name: "tight budget downgrades to direct",
			request: Request{
				TaskBrief: "Compare the two architectures and debate the pros and cons.",
				Budget:    BudgetConstraints{MaxTokens: 500, MaxRounds: 1},
			},
			want: "DIRECT",
		},
	}

	for _, tc := range tests {
		t.Run(tc.name, func(t *testing.T) {
			selection, err := selector.Select(context.Background(), tc.request)
			if err != nil {
				t.Fatalf("Select() error = %v", err)
			}
			if selection.Mode != tc.want {
				t.Fatalf("Select() mode = %s, want %s", selection.Mode, tc.want)
			}
			if selection.RecommendedBudget.Tokens <= 0 {
				t.Fatalf("recommended budget tokens must be positive, got %d", selection.RecommendedBudget.Tokens)
			}
		})
	}
}

func TestRuleBasedSelectorReturnsErrorWhenNoModeFits(t *testing.T) {
	selector := NewRuleBasedSelector()

	_, err := selector.Select(context.Background(), Request{
		TaskBrief: "Solve a trivial task.",
		Budget:    BudgetConstraints{MaxTokens: 1, MaxRounds: 1, MaxCost: 0.0001, MaxTimeMS: 1},
	})
	if err != ErrNoModeFits {
		t.Fatalf("Select() error = %v, want %v", err, ErrNoModeFits)
	}
}

func TestScoreAndDetectSpecialMode(t *testing.T) {
	brief := "First write a Python function, then explain it? Why does it work?"
	if got := Score(brief); got < 4 {
		t.Fatalf("Score() = %d, want at least 4", got)
	}
	if got := DetectSpecialMode("Compare both options and argue both sides."); got != "DEBATE" {
		t.Fatalf("DetectSpecialMode() = %s, want DEBATE", got)
	}
	if got := DetectSpecialMode("Write code in Python to solve the problem."); got != "CODE_AS_REASONING" {
		t.Fatalf("DetectSpecialMode() = %s, want CODE_AS_REASONING", got)
	}
}
