package event_streamer

import (
	"context"
	"encoding/json"
	"errors"
	"io"
	"log/slog"
	"testing"
	"time"

	simulationv1 "github.com/musematic/simulation-controller/api/grpc/v1"
	"github.com/stretchr/testify/require"
	"google.golang.org/protobuf/types/known/timestamppb"
	corev1 "k8s.io/api/core/v1"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	"k8s.io/apimachinery/pkg/watch"
	"k8s.io/client-go/kubernetes/fake"
	k8stesting "k8s.io/client-go/testing"
)

type recordingProducer struct {
	topics []string
	keys   []string
	err    error
}

func (r *recordingProducer) Produce(topic, key string, _ []byte) error {
	r.topics = append(r.topics, topic)
	r.keys = append(r.keys, key)
	return r.err
}

type fakeWatcher struct {
	fanout *FanoutRegistry
	events []*simulationv1.SimulationEvent
	calls  int
	done   chan struct{}
}

func (f *fakeWatcher) Watch(ctx context.Context, simulationID string) error {
	f.calls++
	for _, event := range f.events {
		f.fanout.Publish(simulationID, event)
		if isTerminalEvent(event.GetEventType()) {
			f.fanout.Close(simulationID)
		}
	}
	if f.done != nil {
		<-ctx.Done()
		close(f.done)
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

	producer.err = errors.New("kafka unavailable")
	watcher.Logger = slog.New(slog.NewTextHandler(io.Discard, nil))
	watcher.publish(event)
	require.Len(t, producer.topics, 2)
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

	emptyPayload, err := MarshalEventEnvelope(nil)
	require.NoError(t, err)
	require.JSONEq(t, `{}`, string(emptyPayload))
}

func TestPodEventTranslationAndTerminalMappings(t *testing.T) {
	t.Parallel()

	require.Nil(t, translatePodEvent("sim-1", watch.Event{Object: &corev1.ConfigMap{}}))
	require.Nil(t, translatePodEvent("sim-1", watch.Event{Type: watch.Modified, Object: &corev1.Pod{}}))

	running := translatePodEvent("sim-1", watch.Event{Type: watch.Modified, Object: &corev1.Pod{
		ObjectMeta: metav1.ObjectMeta{Name: "pod-1"},
		Status:     corev1.PodStatus{Phase: corev1.PodRunning},
	}})
	require.Equal(t, "POD_RUNNING", running.GetEventType())

	for _, tc := range []struct {
		eventType watch.EventType
		phase     corev1.PodPhase
		expected  string
	}{
		{eventType: watch.Added, expected: "POD_CREATED"},
		{eventType: watch.Deleted, expected: "TERMINATED"},
		{eventType: watch.Modified, phase: corev1.PodSucceeded, expected: "POD_COMPLETED"},
		{eventType: watch.Modified, phase: corev1.PodFailed, expected: "POD_FAILED"},
	} {
		eventType, _ := podEventType(tc.eventType, &corev1.Pod{Status: corev1.PodStatus{Phase: tc.phase}})
		require.Equal(t, tc.expected, eventType)
	}

	oomEvent, _ := podEventType(watch.Modified, &corev1.Pod{Status: corev1.PodStatus{
		Phase: corev1.PodFailed,
		ContainerStatuses: []corev1.ContainerStatus{{
			LastTerminationState: corev1.ContainerState{Terminated: &corev1.ContainerStateTerminated{Reason: "OOMKilled"}},
		}},
	}})
	require.Equal(t, "POD_OOM", oomEvent)
	require.True(t, hasOOMKill(&corev1.Pod{Status: corev1.PodStatus{
		ContainerStatuses: []corev1.ContainerStatus{{
			State: corev1.ContainerState{Terminated: &corev1.ContainerStateTerminated{Reason: "OOMKilled"}},
		}},
	}}))
	require.True(t, isTerminalEvent("POD_OOM"))
	require.Equal(t, "simulation.artifact_collected", kafkaEventType("ARTIFACT_COLLECTED"))
	require.Equal(t, "simulation.ate_scenario_completed", kafkaEventType("ATE_SCENARIO_COMPLETED"))
	require.Equal(t, "simulation.terminated", kafkaEventType("TERMINATED"))
	require.Equal(t, "simulation.failed", kafkaEventType("POD_OOM"))
	require.Equal(t, "custom.event", kafkaEventType("CUSTOM_EVENT"))
}

func TestPodWatcherWatchHandlesErrorsClosedStreamsAndCancellation(t *testing.T) {
	t.Parallel()

	client := fake.NewSimpleClientset()
	client.PrependWatchReactor("pods", func(k8stesting.Action) (bool, watch.Interface, error) {
		return true, nil, errors.New("watch failed")
	})
	err := (&PodWatcher{Client: client, Namespace: "sim-ns"}).Watch(context.Background(), "sim-1")
	require.EqualError(t, err, "watch failed")

	closedWatch := watch.NewFake()
	closedClient := fake.NewSimpleClientset()
	closedClient.PrependWatchReactor("pods", func(k8stesting.Action) (bool, watch.Interface, error) {
		closedWatch.Stop()
		return true, closedWatch, nil
	})
	require.NoError(t, (&PodWatcher{Client: closedClient, Namespace: "sim-ns"}).Watch(context.Background(), "sim-1"))

	cancelWatch := watch.NewFake()
	cancelClient := fake.NewSimpleClientset()
	cancelClient.PrependWatchReactor("pods", func(k8stesting.Action) (bool, watch.Interface, error) {
		return true, cancelWatch, nil
	})
	ctx, cancel := context.WithCancel(context.Background())
	cancel()
	require.ErrorIs(t, (&PodWatcher{Client: cancelClient, Namespace: "sim-ns"}).Watch(ctx, "sim-1"), context.Canceled)
}

func TestPodWatcherWatchPublishesAndClosesOnTerminalEvent(t *testing.T) {
	fakeWatch := watch.NewFake()
	client := fake.NewSimpleClientset()
	client.PrependWatchReactor("pods", func(k8stesting.Action) (bool, watch.Interface, error) {
		return true, fakeWatch, nil
	})
	fanout := NewFanoutRegistry(2)
	watcher := &PodWatcher{Client: client, Namespace: "sim-ns", Fanout: fanout}
	ch := fanout.Subscribe("sim-1")

	errCh := make(chan error, 1)
	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()
	go func() {
		errCh <- watcher.Watch(ctx, "sim-1")
	}()

	fakeWatch.Add(&corev1.Pod{ObjectMeta: metav1.ObjectMeta{Name: "pod-1"}, Status: corev1.PodStatus{Phase: corev1.PodRunning}})
	require.Equal(t, "POD_CREATED", (<-ch).GetEventType())
	fakeWatch.Modify(&corev1.Pod{ObjectMeta: metav1.ObjectMeta{Name: "pod-1"}, Status: corev1.PodStatus{Phase: corev1.PodSucceeded}})
	require.Equal(t, "POD_COMPLETED", (<-ch).GetEventType())

	require.NoError(t, <-errCh)
	_, ok := <-ch
	require.False(t, ok)
}

func TestPodWatcherNilClientNoOps(t *testing.T) {
	require.NoError(t, (&PodWatcher{}).Watch(context.Background(), "sim-1"))
	var watcher *PodWatcher
	require.NoError(t, watcher.Watch(context.Background(), "sim-1"))
}

func TestFanoutHelpersCoverDefaultsAndUnsubscribe(t *testing.T) {
	t.Parallel()

	fanout := NewFanoutRegistry(0)
	first := fanout.Subscribe("sim-1")
	second := fanout.Subscribe("sim-1")
	require.Equal(t, 2, fanout.SubscriberCount("sim-1"))

	fanout.Unsubscribe("sim-1", first)
	require.Equal(t, 1, fanout.SubscriberCount("sim-1"))

	fanout.Publish("sim-1", nil)
	select {
	case <-second:
		t.Fatal("unexpected event")
	default:
	}
}

func TestStreamerWatchReferenceCountingAndSendErrors(t *testing.T) {
	t.Parallel()

	fanout := NewFanoutRegistry(2)
	watcher := &fakeWatcher{fanout: fanout, done: make(chan struct{})}
	streamer := NewStreamer(fanout, watcher)

	ctx, cancel := context.WithCancel(context.Background())
	errCh := make(chan error, 1)
	go func() {
		errCh <- streamer.Stream(ctx, "sim-1", func(event *simulationv1.SimulationEvent) error {
			return errors.New("send failed")
		})
	}()

	require.Eventually(t, func() bool {
		return fanout.SubscriberCount("sim-1") == 1
	}, time.Second, 10*time.Millisecond)
	fanout.Publish("sim-1", &simulationv1.SimulationEvent{SimulationId: "sim-1", EventType: "POD_RUNNING"})
	require.EqualError(t, <-errCh, "send failed")
	cancel()
	<-watcher.done
	require.Equal(t, 1, watcher.calls)
}

func TestStreamerHelpersCoverNilCancellationAndReferenceBranches(t *testing.T) {
	t.Parallel()

	var nilStreamer *Streamer
	require.NoError(t, nilStreamer.Stream(context.Background(), "sim-1", func(*simulationv1.SimulationEvent) error {
		return nil
	}))
	nilStreamer.ensureWatch("sim-1")
	nilStreamer.releaseWatch("sim-1")

	streamer := NewStreamer(NewFanoutRegistry(1), nil)
	streamer.ensureWatch("sim-1")
	streamer.releaseWatch("missing")

	fanout := NewFanoutRegistry(1)
	watcher := &fakeWatcher{fanout: fanout, done: make(chan struct{})}
	streamer = NewStreamer(fanout, watcher)
	streamer.ensureWatch("sim-1")
	streamer.ensureWatch("sim-1")
	require.Equal(t, 2, streamer.watches["sim-1"].refs)
	streamer.releaseWatch("sim-1")
	require.Equal(t, 1, streamer.watches["sim-1"].refs)
	streamer.releaseWatch("sim-1")
	<-watcher.done

	ctx, cancel := context.WithCancel(context.Background())
	cancel()
	err := NewStreamer(NewFanoutRegistry(1), nil).Stream(ctx, "sim-1", func(*simulationv1.SimulationEvent) error {
		return nil
	})
	require.ErrorIs(t, err, context.Canceled)
}
