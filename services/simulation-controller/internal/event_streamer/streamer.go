package event_streamer

import (
	"context"
	"sync"

	simulationv1 "github.com/musematic/simulation-controller/api/grpc/v1"
)

type EventStreamer interface {
	Stream(ctx context.Context, simulationID string, send func(*simulationv1.SimulationEvent) error) error
}

type watcher interface {
	Watch(ctx context.Context, simulationID string) error
}

type activeWatch struct {
	refs   int
	cancel context.CancelFunc
}

type Streamer struct {
	Fanout  *FanoutRegistry
	Watcher watcher

	mu      sync.Mutex
	watches map[string]*activeWatch
}

func NewStreamer(fanout *FanoutRegistry, watch watcher) *Streamer {
	return &Streamer{
		Fanout:  fanout,
		Watcher: watch,
		watches: map[string]*activeWatch{},
	}
}

func (s *Streamer) Stream(ctx context.Context, simulationID string, send func(*simulationv1.SimulationEvent) error) error {
	if s == nil || s.Fanout == nil {
		return nil
	}

	ch := s.Fanout.Subscribe(simulationID)
	s.ensureWatch(simulationID)
	defer func() {
		s.Fanout.Unsubscribe(simulationID, ch)
		s.releaseWatch(simulationID)
	}()

	for {
		select {
		case <-ctx.Done():
			return ctx.Err()
		case event, ok := <-ch:
			if !ok {
				return nil
			}
			if err := send(event); err != nil {
				return err
			}
			if isTerminalEvent(event.GetEventType()) {
				return nil
			}
		}
	}
}

func (s *Streamer) ensureWatch(simulationID string) {
	if s == nil || s.Watcher == nil {
		return
	}

	s.mu.Lock()
	defer s.mu.Unlock()

	if current, ok := s.watches[simulationID]; ok {
		current.refs++
		return
	}

	ctx, cancel := context.WithCancel(context.Background())
	s.watches[simulationID] = &activeWatch{refs: 1, cancel: cancel}
	go func() {
		_ = s.Watcher.Watch(ctx, simulationID)
	}()
}

func (s *Streamer) releaseWatch(simulationID string) {
	if s == nil {
		return
	}

	s.mu.Lock()
	defer s.mu.Unlock()

	current, ok := s.watches[simulationID]
	if !ok {
		return
	}
	current.refs--
	if current.refs > 0 {
		return
	}
	current.cancel()
	delete(s.watches, simulationID)
}
