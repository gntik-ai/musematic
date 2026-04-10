package events

import (
	"sync"

	runtimev1 "github.com/andrea-mucci/musematic/services/runtime-controller/api/grpc/v1"
)

type FanoutRegistry struct {
	mu      sync.RWMutex
	streams map[string][]chan *runtimev1.RuntimeEvent
}

func NewFanoutRegistry() *FanoutRegistry {
	return &FanoutRegistry{streams: map[string][]chan *runtimev1.RuntimeEvent{}}
}

func (f *FanoutRegistry) Subscribe(executionID string) (<-chan *runtimev1.RuntimeEvent, func()) {
	ch := make(chan *runtimev1.RuntimeEvent, 64)
	f.mu.Lock()
	f.streams[executionID] = append(f.streams[executionID], ch)
	f.mu.Unlock()
	return ch, func() {
		f.mu.Lock()
		defer f.mu.Unlock()
		current := f.streams[executionID]
		next := make([]chan *runtimev1.RuntimeEvent, 0, len(current))
		for _, existing := range current {
			if existing != ch {
				next = append(next, existing)
			}
		}
		if len(next) == 0 {
			delete(f.streams, executionID)
		} else {
			f.streams[executionID] = next
		}
		close(ch)
	}
}

func (f *FanoutRegistry) Publish(event *runtimev1.RuntimeEvent) {
	if event == nil {
		return
	}
	f.mu.RLock()
	streams := append([]chan *runtimev1.RuntimeEvent(nil), f.streams[event.ExecutionId]...)
	f.mu.RUnlock()
	for _, ch := range streams {
		select {
		case ch <- event:
		default:
		}
	}
}
