package event_streamer

import (
	"context"
	"encoding/json"
	"testing"
	"time"

	simulationv1 "github.com/musematic/simulation-controller/api/grpc/v1"
	"github.com/stretchr/testify/require"
	"google.golang.org/protobuf/types/known/timestamppb"
)

type recordingProducer struct {
	topics []string
	keys   []string
}

func (r *recordingProducer) Produce(topic, key string, _ []byte) error {
	r.topics = append(r.topics, topic)
	r.keys = append(r.keys, key)
	return nil
}

type fakeWatcher struct {
	fanout *FanoutRegistry
	events []*simulationv1.SimulationEvent
}

func (f *fakeWatcher) Watch(_ context.Context, simulationID string) error {
	for _, event := range f.events {
		f.fanout.Publish(simulationID, event)
		if isTerminalEvent(event.GetEventType()) {
			f.fanout.Close(simulationID)
		}
	}
	return nil
}

func TestFanoutRegistryDeliversToTwoSubscribers(t *testing.T) {
	t.Parallel()

	fanout := NewFanoutRegistry(2)
	first := fanout.Subscribe("sim-1")
	second := fanout.Subscribe("sim-1")

	event := &simulationv1.SimulationEvent{SimulationId: "sim-1", Simulation: true}
	fanout.Publish("sim-1", event)

	require.Equal(t, event, <-first)
	require.Equal(t, event, <-second)
}

func TestStreamerClosesOnTerminalEvent(t *testing.T) {
	t.Parallel()

	fanout := NewFanoutRegistry(2)
	streamer := NewStreamer(fanout, &fakeWatcher{
		fanout: fanout,
		events: []*simulationv1.SimulationEvent{{
			SimulationId: "sim-1",
			EventType:    "TERMINATED",
			Simulation:   true,
			OccurredAt:   timestamppb.Now(),
		}},
	})

	var received []*simulationv1.SimulationEvent
	err := streamer.Stream(context.Background(), "sim-1", func(event *simulationv1.SimulationEvent) error {
		received = append(received, event)
		return nil
	})

	require.NoError(t, err)
	require.Len(t, received, 1)
	require.Equal(t, "TERMINATED", received[0].GetEventType())
}

func TestPodWatcherPublishUsesSimulationTopic(t *testing.T) {
	t.Parallel()

	fanout := NewFanoutRegistry(2)
	producer := &recordingProducer{}
	watcher := &PodWatcher{Fanout: fanout, Producer: producer}
	subscriber := fanout.Subscribe("sim-1")

	event := &simulationv1.SimulationEvent{
		SimulationId: "sim-1",
		EventType:    "POD_RUNNING",
		Simulation:   true,
		OccurredAt:   timestamppb.New(time.Now()),
	}
	watcher.publish(event)

	require.Equal(t, event, <-subscriber)
	require.Equal(t, []string{"simulation.events"}, producer.topics)
	require.Equal(t, []string{"sim-1"}, producer.keys)
}

func TestMarshalEventEnvelopeMapsEventType(t *testing.T) {
	t.Parallel()

	payload, err := MarshalEventEnvelope(&simulationv1.SimulationEvent{
		SimulationId: "sim-1",
		EventType:    "POD_CREATED",
		Simulation:   true,
		OccurredAt:   timestamppb.Now(),
		Metadata:     map[string]string{"pod_name": "pod-1"},
	})
	require.NoError(t, err)

	var envelope map[string]any
	require.NoError(t, json.Unmarshal(payload, &envelope))
	require.Equal(t, "simulation.created", envelope["event_type"])
	require.Equal(t, true, envelope["simulation"])
}
