package quality_evaluator

import "testing"

func TestStaticEvaluatorScore(t *testing.T) {
	score, err := StaticEvaluator{}.Score("one two three four five")
	if err != nil {
		t.Fatalf("Score() error = %v", err)
	}
	if score <= 0 {
		t.Fatalf("Score() = %v, want positive", score)
	}

	empty, err := StaticEvaluator{}.Score("")
	if err != nil {
		t.Fatalf("Score() error = %v", err)
	}
	if empty != 0 {
		t.Fatalf("Score() = %v, want 0", empty)
	}
}
