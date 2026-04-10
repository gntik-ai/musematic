package event_streamer

import (
	"context"
	"encoding/json"
	"fmt"
	"log/slog"
	"strings"
	"time"

	simulationv1 "github.com/musematic/simulation-controller/api/grpc/v1"
	"github.com/musematic/simulation-controller/internal/sim_manager"
	"google.golang.org/protobuf/types/known/timestamppb"
	corev1 "k8s.io/api/core/v1"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	"k8s.io/apimachinery/pkg/watch"
	"k8s.io/client-go/kubernetes"
)

type Producer interface {
	Produce(topic, key string, value []byte) error
}

type PodWatcher struct {
	Client    kubernetes.Interface
	Namespace string
	Fanout    *FanoutRegistry
	Producer  Producer
	Logger    *slog.Logger
}

func (w *PodWatcher) Watch(ctx context.Context, simulationID string) error {
	if w == nil || w.Client == nil {
		return nil
	}

	stream, err := w.Client.CoreV1().Pods(w.Namespace).Watch(ctx, metav1.ListOptions{
		LabelSelector: fmt.Sprintf("%s=%s", sim_manager.SimulationIDLabelKey, simulationID),
	})
	if err != nil {
		return err
	}
	defer stream.Stop()

	for {
		select {
		case <-ctx.Done():
			return ctx.Err()
		case event, ok := <-stream.ResultChan():
			if !ok {
				return nil
			}
			simulationEvent := translatePodEvent(simulationID, event)
			if simulationEvent == nil {
				continue
			}
			w.publish(simulationEvent)
			if isTerminalEvent(simulationEvent.GetEventType()) {
				if w.Fanout != nil {
					w.Fanout.Close(simulationID)
				}
				return nil
			}
		}
	}
}

func (w *PodWatcher) publish(event *simulationv1.SimulationEvent) {
	if w.Fanout != nil {
		w.Fanout.Publish(event.GetSimulationId(), event)
	}
	if w.Producer == nil {
		return
	}

	payload, err := MarshalEventEnvelope(event)
	if err != nil {
		if w.Logger != nil {
			w.Logger.Error("marshal event envelope failed", "error", err)
		}
		return
	}
	if err := w.Producer.Produce("simulation.events", event.GetSimulationId(), payload); err != nil && w.Logger != nil {
		w.Logger.Error("publish simulation event failed", "error", err, "simulation_id", event.GetSimulationId())
	}
}

func MarshalEventEnvelope(event *simulationv1.SimulationEvent) ([]byte, error) {
	if event == nil {
		return json.Marshal(map[string]any{})
	}

	envelope := map[string]any{
		"event_type":    kafkaEventType(event.GetEventType()),
		"version":       "1.0",
		"source":        "simulation-controller",
		"simulation_id": event.GetSimulationId(),
		"simulation":    event.GetSimulation(),
		"occurred_at":   event.GetOccurredAt().AsTime().UTC().Format(time.RFC3339),
		"payload": map[string]any{
			"detail":   event.GetDetail(),
			"metadata": event.GetMetadata(),
		},
	}
	return json.Marshal(envelope)
}

func translatePodEvent(simulationID string, event watch.Event) *simulationv1.SimulationEvent {
	pod, ok := event.Object.(*corev1.Pod)
	if !ok {
		return nil
	}

	eventType, detail := podEventType(event.Type, pod)
	if eventType == "" {
		return nil
	}
	return &simulationv1.SimulationEvent{
		SimulationId: simulationID,
		EventType:    eventType,
		Detail:       detail,
		Simulation:   true,
		OccurredAt:   timestamppb.Now(),
		Metadata: map[string]string{
			"pod_name": pod.Name,
			"phase":    string(pod.Status.Phase),
		},
	}
}

func podEventType(eventType watch.EventType, pod *corev1.Pod) (string, string) {
	switch eventType {
	case watch.Added:
		return "POD_CREATED", "simulation pod created"
	case watch.Deleted:
		return "TERMINATED", "simulation pod deleted"
	case watch.Modified:
		switch pod.Status.Phase {
		case corev1.PodRunning:
			return "POD_RUNNING", "simulation pod is running"
		case corev1.PodSucceeded:
			return "POD_COMPLETED", "simulation pod completed successfully"
		case corev1.PodFailed:
			if hasOOMKill(pod) {
				return "POD_OOM", "simulation pod was OOM killed"
			}
			return "POD_FAILED", "simulation pod failed"
		}
	}
	return "", ""
}

func hasOOMKill(pod *corev1.Pod) bool {
	for _, status := range pod.Status.ContainerStatuses {
		if strings.EqualFold(status.LastTerminationState.Terminated.Reason, "OOMKilled") {
			return true
		}
		if strings.EqualFold(status.State.Terminated.Reason, "OOMKilled") {
			return true
		}
	}
	return false
}

func isTerminalEvent(eventType string) bool {
	switch eventType {
	case "POD_COMPLETED", "POD_FAILED", "POD_OOM", "TERMINATED":
		return true
	default:
		return false
	}
}

func kafkaEventType(eventType string) string {
	switch eventType {
	case "POD_CREATED":
		return "simulation.created"
	case "POD_RUNNING":
		return "simulation.running"
	case "POD_COMPLETED":
		return "simulation.completed"
	case "POD_FAILED", "POD_OOM":
		return "simulation.failed"
	case "ARTIFACT_COLLECTED":
		return "simulation.artifact_collected"
	case "ATE_SCENARIO_COMPLETED":
		return "simulation.ate_scenario_completed"
	case "TERMINATED":
		return "simulation.terminated"
	default:
		return strings.ToLower(strings.ReplaceAll(eventType, "_", "."))
	}
}
