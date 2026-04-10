package redis

import (
	"context"
	"errors"
	"testing"
)

type fakeScript struct {
	result any
	err    error
}

func (f fakeScript) Run(context.Context, string, int64, string, int64) (any, error) {
	if f.err != nil {
		return nil, f.err
	}
	return f.result, nil
}

type fakeCloser struct {
	closed bool
}

func (f *fakeCloser) Close() error {
	f.closed = true
	return nil
}

func TestConversionHelpers(t *testing.T) {
	if got := toInt64(int64(5)); got != 5 {
		t.Fatalf("toInt64() = %d, want 5", got)
	}
	if got := toInt64("7"); got != 7 {
		t.Fatalf("toInt64() = %d, want 7", got)
	}
	if got := toFloat64(1.5); got != 1.5 {
		t.Fatalf("toFloat64() = %v, want 1.5", got)
	}
	if got := toFloat64("2.5"); got != 2.5 {
		t.Fatalf("toFloat64() = %v, want 2.5", got)
	}
	if got := toInt64(true); got != 0 {
		t.Fatalf("toInt64() = %d, want 0 for unsupported type", got)
	}
	if got := toFloat64(true); got != 0 {
		t.Fatalf("toFloat64() = %v, want 0 for unsupported type", got)
	}
}

func TestNewClusterClientRequiresLuaScript(t *testing.T) {
	if _, err := NewClusterClient([]string{"127.0.0.1:6379"}, ""); err == nil {
		t.Fatal("expected missing lua script error from package-local cwd")
	}
}

func TestDecrementBudgetResponses(t *testing.T) {
	client := &BudgetClient{
		client: &fakeCloser{},
		budgetScript: fakeScript{
			result: []interface{}{int64(1), int64(90), int64(4), "1.5", "250"},
		},
	}

	result, err := client.DecrementBudget(context.Background(), "exec-1", "step-1", "tokens", 10)
	if err != nil {
		t.Fatalf("DecrementBudget() error = %v", err)
	}
	if !result.Allowed || result.RemainingTokens != 90 || result.RemainingRounds != 4 || result.RemainingCost != 1.5 || result.RemainingTimeMS != 250 {
		t.Fatalf("unexpected budget result: %+v", result)
	}
}

func TestDecrementBudgetErrors(t *testing.T) {
	var nilClient *BudgetClient
	if _, err := nilClient.DecrementBudget(context.Background(), "exec", "step", "tokens", 1); err == nil {
		t.Fatal("expected error for nil client")
	}

	client := &BudgetClient{
		client:       &fakeCloser{},
		budgetScript: fakeScript{err: errors.New("redis failed")},
	}
	if _, err := client.DecrementBudget(context.Background(), "exec", "step", "tokens", 1); err == nil || err.Error() != "redis failed" {
		t.Fatalf("DecrementBudget() error = %v, want redis failed", err)
	}

	client.budgetScript = fakeScript{result: "not-a-slice"}
	if _, err := client.DecrementBudget(context.Background(), "exec", "step", "tokens", 1); err == nil || err.Error() != "unexpected redis budget response" {
		t.Fatalf("DecrementBudget() error = %v, want unexpected redis budget response", err)
	}

	client.budgetScript = fakeScript{result: []interface{}{int64(1), int64(2)}}
	if _, err := client.DecrementBudget(context.Background(), "exec", "step", "tokens", 1); err == nil || err.Error() != "unexpected redis budget response" {
		t.Fatalf("DecrementBudget() error = %v, want unexpected redis budget response", err)
	}
}

func TestCloseHandlesNilAndInitializedClient(t *testing.T) {
	var nilClient *BudgetClient
	if err := nilClient.Close(); err != nil {
		t.Fatalf("Close() error = %v", err)
	}

	closer := &fakeCloser{}
	client := &BudgetClient{client: closer}
	if err := client.Close(); err != nil {
		t.Fatalf("Close() error = %v", err)
	}
	if !closer.closed {
		t.Fatal("expected close to be invoked")
	}
}
