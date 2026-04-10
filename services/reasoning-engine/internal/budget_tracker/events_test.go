package budget_tracker

import (
	"context"
	"fmt"
	"strconv"
	"sync"
	"testing"
	"time"
)

type fakeStore struct {
	mu     sync.Mutex
	hashes map[string]map[string]string
}

func newFakeStore() *fakeStore {
	return &fakeStore{hashes: map[string]map[string]string{}}
}

func (s *fakeStore) Exists(_ context.Context, key string) (int64, error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	if _, ok := s.hashes[key]; ok {
		return 1, nil
	}
	return 0, nil
}

func (s *fakeStore) HSet(_ context.Context, key string, values map[string]any) error {
	s.mu.Lock()
	defer s.mu.Unlock()
	if _, ok := s.hashes[key]; !ok {
		s.hashes[key] = map[string]string{}
	}
	for field, value := range values {
		s.hashes[key][field] = stringify(value)
	}
	return nil
}

func (s *fakeStore) HSetFields(_ context.Context, key string, values ...any) error {
	s.mu.Lock()
	defer s.mu.Unlock()
	if _, ok := s.hashes[key]; !ok {
		s.hashes[key] = map[string]string{}
	}
	for i := 0; i < len(values); i += 2 {
		s.hashes[key][values[i].(string)] = stringify(values[i+1])
	}
	return nil
}

func (s *fakeStore) Expire(context.Context, string, time.Duration) error {
	return nil
}

func (s *fakeStore) EvalSha(_ context.Context, _ string, keys []string, args ...any) (any, error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	key := keys[0]
	field := args[0].(string)
	amount := toFloatAny(args[1])
	current := toFloat(s.hashes[key][field])
	maxField := "max_" + field[5:]
	maxValue := toFloat(s.hashes[key][maxField])
	if current+amount > maxValue {
		return float64(-1), nil
	}
	current += amount
	s.hashes[key][field] = stringify(current)
	return current, nil
}

func (s *fakeStore) HGetAll(_ context.Context, key string) (map[string]string, error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	current := s.hashes[key]
	out := make(map[string]string, len(current))
	for field, value := range current {
		out[field] = value
	}
	return out, nil
}

func TestRedisTrackerAllocateDecrementAndStatus(t *testing.T) {
	registry := NewEventRegistry()
	tracker := &RedisTracker{
		store:      newFakeStore(),
		scripts:    map[string]string{"budget_decrement": "budget_decrement"},
		registry:   registry,
		defaultTTL: 3600,
		now:        func() time.Time { return time.UnixMilli(1_000).UTC() },
	}

	if err := tracker.Allocate(context.Background(), "exec-1", "step-1", BudgetAllocation{
		Tokens: 1000,
		Rounds: 10,
		Cost:   5,
		TimeMS: 1000,
	}, 0); err != nil {
		t.Fatalf("Allocate() error = %v", err)
	}

	status, err := tracker.GetStatus(context.Background(), "exec-1", "step-1")
	if err != nil {
		t.Fatalf("GetStatus() error = %v", err)
	}
	if status.Status != "ALLOCATED" {
		t.Fatalf("status = %s, want ALLOCATED", status.Status)
	}

	value, err := tracker.Decrement(context.Background(), "exec-1", "step-1", "tokens", 800)
	if err != nil {
		t.Fatalf("Decrement() error = %v", err)
	}
	if value != 800 {
		t.Fatalf("Decrement() value = %v, want 800", value)
	}

	status, err = tracker.GetStatus(context.Background(), "exec-1", "step-1")
	if err != nil {
		t.Fatalf("GetStatus() error = %v", err)
	}
	if status.Used.Tokens != 800 {
		t.Fatalf("used tokens = %d, want 800", status.Used.Tokens)
	}

	if err := tracker.Allocate(context.Background(), "exec-1", "step-1", BudgetAllocation{Tokens: 1}, 0); err != ErrAlreadyExists {
		t.Fatalf("Allocate duplicate error = %v, want %v", err, ErrAlreadyExists)
	}
}

func TestRedisTrackerExceededPublishesFinalEvent(t *testing.T) {
	registry := NewEventRegistry()
	tracker := &RedisTracker{
		store:      newFakeStore(),
		scripts:    map[string]string{"budget_decrement": "budget_decrement"},
		registry:   registry,
		defaultTTL: 3600,
		now:        func() time.Time { return time.UnixMilli(1_000).UTC() },
	}

	if err := tracker.Allocate(context.Background(), "exec-2", "step-1", BudgetAllocation{Tokens: 1000}, 0); err != nil {
		t.Fatalf("Allocate() error = %v", err)
	}

	ch := registry.Subscribe(Key("exec-2", "step-1"))
	defer registry.Unsubscribe(Key("exec-2", "step-1"), ch)

	if _, err := tracker.Decrement(context.Background(), "exec-2", "step-1", "tokens", 1001); err != ErrBudgetExceeded {
		t.Fatalf("Decrement() error = %v, want %v", err, ErrBudgetExceeded)
	}

	event := recvEvent(t, ch)
	if event.EventType != "EXCEEDED" {
		t.Fatalf("event type = %s, want EXCEEDED", event.EventType)
	}
}

func TestEventRegistryThresholdFanOutAndNoReplay(t *testing.T) {
	registry := NewEventRegistry()
	key := Key("exec-3", "step-1")
	registry.Register(key)

	first := registry.Subscribe(key)
	second := registry.Subscribe(key)
	defer registry.Unsubscribe(key, first)
	defer registry.Unsubscribe(key, second)

	status := &BudgetStatus{
		ExecutionID: "exec-3",
		StepID:      "step-1",
		Limits:      BudgetAllocation{Tokens: 1000},
		Used:        BudgetAllocation{Tokens: 800},
	}
	registry.EvaluateAndPublish(key, status)

	if event := recvEvent(t, first); event.EventType != "THRESHOLD_80" {
		t.Fatalf("first event = %s, want THRESHOLD_80", event.EventType)
	}
	if event := recvEvent(t, second); event.EventType != "THRESHOLD_80" {
		t.Fatalf("second event = %s, want THRESHOLD_80", event.EventType)
	}

	late := registry.Subscribe(key)
	defer registry.Unsubscribe(key, late)

	status.Used.Tokens = 900
	registry.EvaluateAndPublish(key, status)

	if event := recvEvent(t, first); event.EventType != "THRESHOLD_90" {
		t.Fatalf("first event = %s, want THRESHOLD_90", event.EventType)
	}
	if event := recvEvent(t, second); event.EventType != "THRESHOLD_90" {
		t.Fatalf("second event = %s, want THRESHOLD_90", event.EventType)
	}
	if event := recvEvent(t, late); event.EventType != "THRESHOLD_90" {
		t.Fatalf("late subscriber event = %s, want THRESHOLD_90", event.EventType)
	}

	select {
	case event := <-late:
		t.Fatalf("unexpected replayed event: %+v", event)
	default:
	}

	registry.EvaluateAndPublish(key, status)
	select {
	case event := <-first:
		t.Fatalf("threshold should not be re-emitted, got %+v", event)
	default:
	}
}

func TestEventRegistryCloseClosesSubscribers(t *testing.T) {
	registry := NewEventRegistry()
	key := Key("exec-4", "step-1")
	registry.Register(key)

	ch := registry.Subscribe(key)
	registry.Close(key, BudgetEvent{ExecutionID: "exec-4", StepID: "step-1", EventType: "COMPLETED"})

	event, ok := <-ch
	if !ok {
		t.Fatal("expected final event before channel close")
	}
	if event.EventType != "COMPLETED" {
		t.Fatalf("event type = %s, want COMPLETED", event.EventType)
	}
	if _, open := <-ch; open {
		t.Fatal("channel should be closed")
	}
}

func TestTrackerHelperBranches(t *testing.T) {
	registry := NewEventRegistry()
	tracker := &RedisTracker{
		store:      newFakeStore(),
		scripts:    map[string]string{"budget_decrement": "budget_decrement"},
		registry:   registry,
		defaultTTL: 3600,
		now:        func() time.Time { return time.UnixMilli(2_000).UTC() },
	}

	if fieldForDimension("unknown") != "" {
		t.Fatal("expected empty field for unknown dimension")
	}
	if !exhaustedByTime(&BudgetStatus{Limits: BudgetAllocation{TimeMS: 10}, Used: BudgetAllocation{TimeMS: 10}}) {
		t.Fatal("expected exhaustedByTime() to return true")
	}
	if _, err := parseFloat(struct{}{}); err == nil {
		t.Fatal("expected parseFloat() to fail for unsupported type")
	}
	if parseInt64("1.5") != 1 {
		t.Fatalf("parseInt64() did not parse float string")
	}
	if parseFloat64("nope") != 0 {
		t.Fatalf("parseFloat64() should return zero on invalid input")
	}

	if err := tracker.Allocate(context.Background(), "exec-5", "step-1", BudgetAllocation{Tokens: 10, TimeMS: 10}, 0); err != nil {
		t.Fatalf("Allocate() error = %v", err)
	}
	tracker.now = func() time.Time { return time.UnixMilli(3_000).UTC() }
	if _, err := tracker.Decrement(context.Background(), "exec-5", "step-1", "tokens", 1); err != ErrBudgetExceeded {
		t.Fatalf("Decrement() error = %v, want %v", err, ErrBudgetExceeded)
	}

	registry.Register("manual")
	if !registry.Exists("manual") {
		t.Fatal("expected Exists() to return true")
	}
	registry.PublishExceeded("manual", &BudgetStatus{
		ExecutionID: "exec",
		StepID:      "step",
		Limits:      BudgetAllocation{Cost: 1},
		Used:        BudgetAllocation{Cost: 1},
	}, "cost")
}

func recvEvent(t *testing.T, ch <-chan BudgetEvent) BudgetEvent {
	t.Helper()
	select {
	case event := <-ch:
		return event
	case <-time.After(200 * time.Millisecond):
		t.Fatal("timed out waiting for budget event")
		return BudgetEvent{}
	}
}

func stringify(value any) string {
	switch typed := value.(type) {
	case int:
		return strconv.Itoa(typed)
	case int64:
		return strconv.FormatInt(typed, 10)
	case float64:
		return strconv.FormatFloat(typed, 'f', -1, 64)
	case string:
		return typed
	default:
		return fmt.Sprintf("%v", value)
	}
}

func toFloat(value string) float64 {
	parsed, _ := strconv.ParseFloat(value, 64)
	return parsed
}

func toFloatAny(value any) float64 {
	switch typed := value.(type) {
	case int:
		return float64(typed)
	case int64:
		return float64(typed)
	case float64:
		return typed
	case string:
		return toFloat(typed)
	default:
		return 0
	}
}
