package event_streamer

import (
	"sync"

	simulationv1 "github.com/musematic/simulation-controller/api/grpc/v1"
)

type FanoutRegistry struct {
	mu       sync.RWMutex
	streams  map[string][]chan *simulationv1.SimulationEvent
	capacity int
}

func NewFanoutRegistry(capacity int) *FanoutRegistry {
	if capacity <= 0 {
		capacity = 32
	}
	return &FanoutRegistry{
		streams:  map[string][]chan *simulationv1.SimulationEvent{},
		capacity: capacity,
	}
}

func (f *FanoutRegistry) Subscribe(simulationID string) <-chan *simulationv1.SimulationEvent {
	ch := make(chan *simulationv1.SimulationEvent, f.capacity)
	f.mu.Lock()
	f.streams[simulationID] = append(f.streams[simulationID], ch)
	f.mu.Unlock()
	return ch
}

func (f *FanoutRegistry) Unsubscribe(simulationID string, ch <-chan *simulationv1.SimulationEvent) {
	f.mu.Lock()
	defer f.mu.Unlock()

	current := f.streams[simulationID]
	next := make([]chan *simulationv1.SimulationEvent, 0, len(current))
	for _, existing := range current {
		if (<-chan *simulationv1.SimulationEvent)(existing) == ch {
			close(existing)
			continue
		}
		next = append(next, existing)
	}
	if len(next) == 0 {
		delete(f.streams, simulationID)
		return
	}
	f.streams[simulationID] = next
}

func (f *FanoutRegistry) Publish(simulationID string, event *simulationv1.SimulationEvent) {
	if f == nil || event == nil {
		return
	}

	f.mu.RLock()
	streams := append([]chan *simulationv1.SimulationEvent(nil), f.streams[simulationID]...)
	f.mu.RUnlock()
	for _, ch := range streams {
		select {
		case ch <- event:
		default:
		}
	}
}

func (f *FanoutRegistry) Close(simulationID string) {
	if f == nil {
		return
	}

	f.mu.Lock()
	defer f.mu.Unlock()
	for _, ch := range f.streams[simulationID] {
		close(ch)
	}
	delete(f.streams, simulationID)
}

func (f *FanoutRegistry) SubscriberCount(simulationID string) int {
	f.mu.RLock()
	defer f.mu.RUnlock()
	return len(f.streams[simulationID])
}
