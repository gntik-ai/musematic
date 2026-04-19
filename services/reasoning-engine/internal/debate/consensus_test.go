package debate

import (
	"errors"
	"testing"
)

type evaluatorStub struct {
	scores map[string]float64
	err    error
}

func (s evaluatorStub) Score(hypothesis string) (float64, error) {
	if s.err != nil {
		return 0, s.err
	}
	return s.scores[hypothesis], nil
}

func TestConsensusDetector(t *testing.T) {
	tests := []struct {
		name          string
		contributions []RoundContribution
		evaluator     evaluatorStub
		epsilon       float64
		want          bool
		wantErr       string
	}{
		{
			name:          "requires at least two synthesis steps",
			contributions: []RoundContribution{{StepType: "synthesis", Content: "one"}},
			want:          false,
		},
		{
			name: "returns true within epsilon",
			contributions: []RoundContribution{
				{StepType: "synthesis", Content: "alpha"},
				{StepType: "synthesis", Content: "beta"},
			},
			evaluator: evaluatorStub{scores: map[string]float64{"alpha": 0.78, "beta": 0.81}},
			epsilon:   0.05,
			want:      true,
		},
		{
			name: "returns false when scores diverge",
			contributions: []RoundContribution{
				{StepType: "synthesis", Content: "alpha"},
				{StepType: "synthesis", Content: "beta"},
			},
			evaluator: evaluatorStub{scores: map[string]float64{"alpha": 0.20, "beta": 0.85}},
			epsilon:   0.05,
			want:      false,
		},
		{
			name: "ignores missed and non-synthesis contributions",
			contributions: []RoundContribution{
				{StepType: "position", Content: "alpha"},
				{StepType: "synthesis", Content: "beta", MissedTurn: true},
				{StepType: "synthesis", Content: "gamma"},
			},
			want: false,
		},
		{
			name: "returns evaluator error",
			contributions: []RoundContribution{
				{StepType: "synthesis", Content: "alpha"},
				{StepType: "synthesis", Content: "beta"},
			},
			evaluator: evaluatorStub{err: errors.New("score failed")},
			wantErr:   "score failed",
		},
	}

	for _, tc := range tests {
		t.Run(tc.name, func(t *testing.T) {
			detector := NewConsensusDetector(tc.evaluator, tc.epsilon)
			got, err := detector.Detect(tc.contributions)
			if tc.wantErr != "" {
				if err == nil || err.Error() != tc.wantErr {
					t.Fatalf("Detect() error = %v, want %s", err, tc.wantErr)
				}
				return
			}
			if err != nil {
				t.Fatalf("Detect() error = %v", err)
			}
			if got != tc.want {
				t.Fatalf("Detect() = %v, want %v", got, tc.want)
			}
		})
	}
}
