package budget_tracker

import (
	"sync"
	"time"
)

type BudgetEvent struct {
	ExecutionID  string
	StepID       string
	EventType    string
	Dimension    string
	CurrentValue float64
	MaxValue     float64
	OccurredAt   time.Time
}

type EventRegistry struct {
	mu         sync.RWMutex
	streams    map[string][]chan BudgetEvent
	activeKeys map[string]struct{}
	emitted    map[string]map[string]map[string]bool
}

func NewEventRegistry() *EventRegistry {
	return &EventRegistry{
		streams:    map[string][]chan BudgetEvent{},
		activeKeys: map[string]struct{}{},
		emitted:    map[string]map[string]map[string]bool{},
	}
}

func (r *EventRegistry) Register(key string) {
	r.mu.Lock()
	defer r.mu.Unlock()
	r.activeKeys[key] = struct{}{}
}

func (r *EventRegistry) Exists(key string) bool {
	r.mu.RLock()
	defer r.mu.RUnlock()
	_, ok := r.activeKeys[key]
	return ok
}

func (r *EventRegistry) Subscribe(key string) chan BudgetEvent {
	ch := make(chan BudgetEvent, 32)
	r.mu.Lock()
	r.streams[key] = append(r.streams[key], ch)
	r.mu.Unlock()
	return ch
}

func (r *EventRegistry) SubscribeIfActive(key string) (chan BudgetEvent, bool) {
	ch := make(chan BudgetEvent, 32)
	r.mu.Lock()
	defer r.mu.Unlock()
	if _, ok := r.activeKeys[key]; !ok {
		return nil, false
	}
	r.streams[key] = append(r.streams[key], ch)
	return ch, true
}

func (r *EventRegistry) SubscriberCount(key string) int {
	r.mu.RLock()
	defer r.mu.RUnlock()
	return len(r.streams[key])
}

func (r *EventRegistry) Unsubscribe(key string, ch chan BudgetEvent) {
	r.mu.Lock()
	defer r.mu.Unlock()
	current := r.streams[key]
	next := make([]chan BudgetEvent, 0, len(current))
	found := false
	for _, existing := range current {
		if existing != ch {
			next = append(next, existing)
		} else {
			found = true
		}
	}
	if len(next) == 0 {
		delete(r.streams, key)
	} else {
		r.streams[key] = next
	}
	if found {
		close(ch)
	}
}

func (r *EventRegistry) Publish(key string, event BudgetEvent) {
	r.mu.RLock()
	streams := append([]chan BudgetEvent(nil), r.streams[key]...)
	r.mu.RUnlock()
	for _, ch := range streams {
		select {
		case ch <- event:
		default:
		}
	}
}

func (r *EventRegistry) EvaluateAndPublish(key string, status *BudgetStatus) {
	if status == nil {
		return
	}

	thresholds := []struct {
		label string
		value float64
	}{
		{label: "THRESHOLD_80", value: 0.80},
		{label: "THRESHOLD_90", value: 0.90},
		{label: "THRESHOLD_100", value: 1.00},
	}

	dimensions := []struct {
		name string
		used float64
		max  float64
	}{
		{name: "tokens", used: float64(status.Used.Tokens), max: float64(status.Limits.Tokens)},
		{name: "rounds", used: float64(status.Used.Rounds), max: float64(status.Limits.Rounds)},
		{name: "cost", used: status.Used.Cost, max: status.Limits.Cost},
		{name: "time", used: float64(status.Used.TimeMS), max: float64(status.Limits.TimeMS)},
	}

	for _, dimension := range dimensions {
		if dimension.max <= 0 {
			continue
		}
		ratio := dimension.used / dimension.max
		for _, threshold := range thresholds {
			if ratio >= threshold.value && r.markThreshold(key, dimension.name, threshold.label) {
				r.Publish(key, BudgetEvent{
					ExecutionID:  status.ExecutionID,
					StepID:       status.StepID,
					EventType:    threshold.label,
					Dimension:    dimension.name,
					CurrentValue: dimension.used,
					MaxValue:     dimension.max,
					OccurredAt:   time.Now().UTC(),
				})
			}
		}
	}
}

func (r *EventRegistry) PublishExceeded(key string, status *BudgetStatus, dimension string) {
	if status == nil {
		return
	}
	r.Close(key, BudgetEvent{
		ExecutionID:  status.ExecutionID,
		StepID:       status.StepID,
		EventType:    "EXCEEDED",
		Dimension:    dimension,
		CurrentValue: currentValue(status, dimension),
		MaxValue:     maxValue(status, dimension),
		OccurredAt:   time.Now().UTC(),
	})
}

func (r *EventRegistry) Close(key string, event BudgetEvent) {
	r.mu.Lock()
	streams := append([]chan BudgetEvent(nil), r.streams[key]...)
	delete(r.streams, key)
	delete(r.activeKeys, key)
	delete(r.emitted, key)
	r.mu.Unlock()

	for _, ch := range streams {
		select {
		case ch <- event:
		default:
		}
		close(ch)
	}
}

func (r *EventRegistry) markThreshold(key, dimension, threshold string) bool {
	r.mu.Lock()
	defer r.mu.Unlock()
	if _, ok := r.emitted[key]; !ok {
		r.emitted[key] = map[string]map[string]bool{}
	}
	if _, ok := r.emitted[key][dimension]; !ok {
		r.emitted[key][dimension] = map[string]bool{}
	}
	if r.emitted[key][dimension][threshold] {
		return false
	}
	r.emitted[key][dimension][threshold] = true
	return true
}

func currentValue(status *BudgetStatus, dimension string) float64 {
	switch dimension {
	case "tokens":
		return float64(status.Used.Tokens)
	case "rounds":
		return float64(status.Used.Rounds)
	case "cost":
		return status.Used.Cost
	case "time":
		return float64(status.Used.TimeMS)
	default:
		return 0
	}
}

func maxValue(status *BudgetStatus, dimension string) float64 {
	switch dimension {
	case "tokens":
		return float64(status.Limits.Tokens)
	case "rounds":
		return float64(status.Limits.Rounds)
	case "cost":
		return status.Limits.Cost
	case "time":
		return float64(status.Limits.TimeMS)
	default:
		return 0
	}
}
