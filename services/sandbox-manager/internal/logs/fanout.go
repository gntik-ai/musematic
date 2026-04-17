package logs

import (
	"sync"

	sandboxv1 "github.com/andrea-mucci/musematic/services/sandbox-manager/api/grpc/v1"
)

type FanoutRegistry struct {
	mu       sync.RWMutex
	streams  map[string][]chan *sandboxv1.SandboxLogLine
	history  map[string][]*sandboxv1.SandboxLogLine
	capacity int
}

func NewFanoutRegistry(capacity int) *FanoutRegistry {
	if capacity <= 0 {
		capacity = 100
	}
	return &FanoutRegistry{
		streams:  map[string][]chan *sandboxv1.SandboxLogLine{},
		history:  map[string][]*sandboxv1.SandboxLogLine{},
		capacity: capacity,
	}
}

func (f *FanoutRegistry) Subscribe(sandboxID string) (<-chan *sandboxv1.SandboxLogLine, func()) {
	ch := make(chan *sandboxv1.SandboxLogLine, f.capacity)
	f.mu.Lock()
	f.streams[sandboxID] = append(f.streams[sandboxID], ch)
	f.mu.Unlock()
	return ch, func() {
		f.mu.Lock()
		defer f.mu.Unlock()
		current := f.streams[sandboxID]
		next := make([]chan *sandboxv1.SandboxLogLine, 0, len(current))
		for _, existing := range current {
			if existing != ch {
				next = append(next, existing)
			}
		}
		if len(next) == 0 {
			delete(f.streams, sandboxID)
		} else {
			f.streams[sandboxID] = next
		}
		close(ch)
	}
}

func (f *FanoutRegistry) Publish(sandboxID string, line *sandboxv1.SandboxLogLine) {
	if line == nil {
		return
	}
	f.mu.Lock()
	f.history[sandboxID] = append(f.history[sandboxID], line)
	streams := append([]chan *sandboxv1.SandboxLogLine(nil), f.streams[sandboxID]...)
	f.mu.Unlock()
	for _, ch := range streams {
		select {
		case ch <- line:
		default:
		}
	}
}

func (f *FanoutRegistry) Buffered(sandboxID string) []*sandboxv1.SandboxLogLine {
	f.mu.RLock()
	defer f.mu.RUnlock()
	items := f.history[sandboxID]
	out := make([]*sandboxv1.SandboxLogLine, 0, len(items))
	out = append(out, items...)
	return out
}

func (f *FanoutRegistry) Close(sandboxID string) {
	f.mu.Lock()
	defer f.mu.Unlock()
	for _, ch := range f.streams[sandboxID] {
		close(ch)
	}
	delete(f.streams, sandboxID)
}
