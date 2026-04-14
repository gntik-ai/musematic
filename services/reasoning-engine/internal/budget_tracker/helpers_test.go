package budget_tracker

import (
	"context"
	"testing"
	"time"

	"github.com/redis/go-redis/v9"
)

func TestBudgetTrackerHelpers(t *testing.T) {
	t.Parallel()

	tracker := NewRedisTracker(nil, nil, nil, nil, 0)
	if tracker.defaultTTL != 3600 {
		t.Fatalf("defaultTTL = %d, want 3600", tracker.defaultTTL)
	}
	if tracker.store != nil {
		t.Fatalf("expected nil store without redis client, got %+v", tracker.store)
	}

	realTracker := NewRedisTracker(redis.NewClient(&redis.Options{Addr: "127.0.0.1:6379"}), nil, nil, nil, 120)
	if realTracker.defaultTTL != 120 {
		t.Fatalf("defaultTTL = %d, want 120", realTracker.defaultTTL)
	}
	if realTracker.store == nil {
		t.Fatal("expected redis-backed store when client is provided")
	}

	if !exhaustedByTime(&BudgetStatus{
		Limits: BudgetAllocation{TimeMS: 100},
		Used:   BudgetAllocation{TimeMS: 100},
	}) {
		t.Fatal("expected exhaustedByTime() to report exhausted budget")
	}
	if exhaustedByTime(nil) {
		t.Fatal("expected nil budget status to be non-exhausted")
	}
	if got := redisKey("exec-1", "step-1"); got != "budget:exec-1:step-1" {
		t.Fatalf("redisKey() = %q", got)
	}
	if got := fieldForDimension("tokens"); got != "used_tokens" {
		t.Fatalf("fieldForDimension(tokens) = %q", got)
	}
	if got := fieldForDimension("rounds"); got != "used_rounds" {
		t.Fatalf("fieldForDimension(rounds) = %q", got)
	}
	if got := fieldForDimension("cost"); got != "used_cost" {
		t.Fatalf("fieldForDimension(cost) = %q", got)
	}
	if got := fieldForDimension("other"); got != "" {
		t.Fatalf("fieldForDimension(other) = %q", got)
	}
	if got, err := parseFloat(int64(5)); err != nil || got != 5 {
		t.Fatalf("parseFloat(int64) = %v, %v", got, err)
	}
	if got, err := parseFloat(3.5); err != nil || got != 3.5 {
		t.Fatalf("parseFloat(float64) = %v, %v", got, err)
	}
	if got, err := parseFloat("2.25"); err != nil || got != 2.25 {
		t.Fatalf("parseFloat(string) = %v, %v", got, err)
	}
	if _, err := parseFloat(struct{}{}); err == nil {
		t.Fatal("expected parseFloat() to reject unsupported types")
	}
	if got := parseInt64(""); got != 0 {
		t.Fatalf("parseInt64(empty) = %d", got)
	}
	if got := parseInt64("15"); got != 15 {
		t.Fatalf("parseInt64(int) = %d", got)
	}
	if got := parseInt64("15.7"); got != 15 {
		t.Fatalf("parseInt64(float) = %d", got)
	}
	if got := parseFloat64(""); got != 0 {
		t.Fatalf("parseFloat64(empty) = %v", got)
	}
	if got := parseFloat64("4.5"); got != 4.5 {
		t.Fatalf("parseFloat64(value) = %v", got)
	}
}

func TestAllocateRejectsInvalidInputWithoutStore(t *testing.T) {
	t.Parallel()

	tracker := &RedisTracker{
		defaultTTL: 60,
		now:        func() time.Time { return time.Unix(0, 0).UTC() },
	}
	if err := tracker.Allocate(context.Background(), "exec-1", "step-1", BudgetAllocation{}, 0); err == nil {
		t.Fatal("expected Allocate() to reject missing redis client")
	}
	if _, err := tracker.Decrement(context.Background(), "exec-1", "step-1", "tokens", 1); err == nil {
		t.Fatal("expected Decrement() to reject missing redis client")
	}
	if _, err := tracker.GetStatus(context.Background(), "exec-1", "step-1"); err == nil {
		t.Fatal("expected GetStatus() to reject missing redis client")
	}
}

func TestGetStatusBranches(t *testing.T) {
	t.Parallel()

	missing := &RedisTracker{store: newFakeStore(), now: func() time.Time { return time.UnixMilli(1_000).UTC() }}
	if _, err := missing.GetStatus(context.Background(), "missing", "step"); err != ErrBudgetNotFound {
		t.Fatalf("GetStatus() error = %v, want %v", err, ErrBudgetNotFound)
	}

	store := newFakeStore()
	_ = store.HSet(context.Background(), redisKey("exec-1", "step-1"), map[string]any{
		"execution_id":    "exec-1",
		"step_id":         "step-1",
		"max_tokens":      10,
		"max_rounds":      2,
		"max_cost":        1.5,
		"max_time_ms":     100,
		"used_tokens":     3,
		"used_rounds":     1,
		"used_cost":       0.5,
		"start_time_ms":   2_000,
		"allocated_at_ms": 1_000,
		"status":          "ACTIVE",
	})
	tracker := &RedisTracker{
		store: store,
		now:   func() time.Time { return time.UnixMilli(1_500).UTC() },
	}
	status, err := tracker.GetStatus(context.Background(), "exec-1", "step-1")
	if err != nil {
		t.Fatalf("GetStatus() error = %v", err)
	}
	if status.Used.TimeMS != 0 {
		t.Fatalf("elapsed time = %d, want clamped 0", status.Used.TimeMS)
	}
}
