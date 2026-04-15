package launcher

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"time"

	runtimev1 "github.com/andrea-mucci/musematic/services/runtime-controller/api/grpc/v1"
	"github.com/andrea-mucci/musematic/services/runtime-controller/internal/events"
	"github.com/andrea-mucci/musematic/services/runtime-controller/internal/state"
	"github.com/google/uuid"
	v1 "k8s.io/api/core/v1"
)

var (
	ErrAlreadyExists   = errors.New("runtime already exists")
	ErrInvalidContract = errors.New("invalid runtime contract")
)

type PodManager interface {
	CreatePod(context.Context, *v1.Pod) (*v1.Pod, error)
	PrepareWarmPod(context.Context, string, *runtimev1.RuntimeContract) error
}

type SecretResolver interface {
	Resolve(context.Context, []string) ([]v1.VolumeProjection, []v1.EnvVar, error)
}

type Store interface {
	InsertRuntime(context.Context, state.RuntimeRecord) error
	GetRuntimeByExecutionID(context.Context, string) (state.RuntimeRecord, error)
	UpdateRuntimeState(context.Context, string, string, string) error
	InsertTaskPlanRecord(context.Context, state.TaskPlanRecord) error
	InsertRuntimeEvent(context.Context, state.RuntimeEventRecord) error
}

type Presigner interface {
	PresignAgentPackageURL(context.Context, string, time.Duration) (string, error)
}

type WarmPoolDispatcher interface {
	Dispatch(context.Context, string, string, uuid.UUID) (string, bool, error)
}

type Launcher struct {
	Namespace  string
	PresignTTL time.Duration
	Store      Store
	Pods       PodManager
	Secrets    SecretResolver
	Presigner  Presigner
	Emitter    *events.EventEmitter
	Fanout     *events.FanoutRegistry
	WarmPool   WarmPoolDispatcher
}

type secretResolverFunc func(context.Context, []string) ([]v1.VolumeProjection, []v1.EnvVar, error)

func (f secretResolverFunc) Resolve(ctx context.Context, refs []string) ([]v1.VolumeProjection, []v1.EnvVar, error) {
	return f(ctx, refs)
}

func (l *Launcher) Launch(ctx context.Context, contract *runtimev1.RuntimeContract) (*runtimev1.RuntimeInfo, bool, error) {
	if contract == nil || contract.CorrelationContext == nil || contract.CorrelationContext.ExecutionId == "" || contract.CorrelationContext.WorkspaceId == "" {
		return nil, false, ErrInvalidContract
	}
	if _, err := l.Store.GetRuntimeByExecutionID(ctx, contract.CorrelationContext.ExecutionId); err == nil {
		return nil, false, ErrAlreadyExists
	} else if !state.IsNotFound(err) {
		return nil, false, err
	}

	runtimeID := uuid.New()
	runtimeRecord := state.RuntimeRecord{
		RuntimeID:          runtimeID,
		ExecutionID:        contract.CorrelationContext.ExecutionId,
		StepID:             contract.StepId,
		WorkspaceID:        contract.CorrelationContext.WorkspaceId,
		AgentFQN:           contract.AgentRevision,
		AgentRevision:      contract.AgentRevision,
		ModelBinding:       json.RawMessage(contract.ModelBinding),
		State:              "pending",
		PodNamespace:       l.Namespace,
		CorrelationContext: mustJSON(contract.CorrelationContext),
		ResourceLimits:     mustJSON(contract.ResourceLimits),
		SecretRefs:         contract.SecretRefs,
	}
	if err := l.Store.InsertRuntime(ctx, runtimeRecord); err != nil {
		return nil, false, err
	}
	if contract.TaskPlanJson != "" {
		if err := l.Store.InsertTaskPlanRecord(ctx, state.TaskPlanRecord{
			ExecutionID: contract.CorrelationContext.ExecutionId,
			StepID:      contract.StepId,
			WorkspaceID: contract.CorrelationContext.WorkspaceId,
			PayloadJSON: json.RawMessage(contract.TaskPlanJson),
		}); err != nil {
			return nil, false, err
		}
	}

	if l.WarmPool != nil {
		if podName, ok, err := l.WarmPool.Dispatch(ctx, contract.CorrelationContext.WorkspaceId, contract.AgentRevision, runtimeID); err != nil {
			return nil, false, err
		} else if ok {
			if err := l.Pods.PrepareWarmPod(ctx, podName, contract); err != nil {
				return nil, false, err
			}
			if err := l.Store.UpdateRuntimeState(ctx, contract.CorrelationContext.ExecutionId, "running", ""); err != nil {
				return nil, false, err
			}
			info := runtimeInfoFromRecord(runtimeRecord, "running", podName)
			l.publishLifecycle(ctx, runtimeID, contract, runtimev1.RuntimeEventType_RUNTIME_EVENT_LAUNCHED, runtimev1.RuntimeState_RUNTIME_STATE_RUNNING, "warm_start")
			return info, true, nil
		}
	}

	presignedURL := fmt.Sprintf("https://packages.invalid/%s", contract.AgentRevision)
	if l.Presigner != nil {
		url, err := l.Presigner.PresignAgentPackageURL(ctx, contract.AgentRevision, l.PresignTTL)
		if err != nil {
			return nil, false, err
		}
		presignedURL = url
	}

	var secretVolumes []v1.VolumeProjection
	var secretEnvs []v1.EnvVar
	if l.Secrets != nil {
		var err error
		secretVolumes, secretEnvs, err = l.Secrets.Resolve(ctx, contract.SecretRefs)
		if err != nil {
			return nil, false, err
		}
	}

	pod := BuildPodSpec(contract, presignedURL, l.Namespace, secretVolumes, secretEnvs)
	createdPod, err := l.Pods.CreatePod(ctx, pod)
	if err != nil {
		return nil, false, err
	}
	if err := l.Store.UpdateRuntimeState(ctx, contract.CorrelationContext.ExecutionId, "running", ""); err != nil {
		return nil, false, err
	}
	l.publishLifecycle(ctx, runtimeID, contract, runtimev1.RuntimeEventType_RUNTIME_EVENT_LAUNCHED, runtimev1.RuntimeState_RUNTIME_STATE_RUNNING, "")
	return runtimeInfoFromRecord(runtimeRecord, "running", createdPod.Name), false, nil
}

func runtimeInfoFromRecord(record state.RuntimeRecord, runtimeState string, podName string) *runtimev1.RuntimeInfo {
	stateValue := runtimev1.RuntimeState_RUNTIME_STATE_PENDING
	if runtimeState == "running" {
		stateValue = runtimev1.RuntimeState_RUNTIME_STATE_RUNNING
	}
	return &runtimev1.RuntimeInfo{
		RuntimeId:     record.RuntimeID.String(),
		ExecutionId:   record.ExecutionID,
		State:         stateValue,
		FailureReason: record.FailureReason,
		PodName:       podName,
		CorrelationContext: &runtimev1.CorrelationContext{
			WorkspaceId: record.WorkspaceID,
			ExecutionId: record.ExecutionID,
		},
	}
}

func (l *Launcher) publishLifecycle(ctx context.Context, runtimeID uuid.UUID, contract *runtimev1.RuntimeContract, eventType runtimev1.RuntimeEventType, stateValue runtimev1.RuntimeState, details string) {
	envelope := events.BuildEnvelope("runtime.launched", runtimeID.String(), contract.CorrelationContext.ExecutionId, contract.CorrelationContext, map[string]any{
		"agent_revision": contract.AgentRevision,
	})
	event := events.RuntimeEventFromEnvelope(envelope, eventType, stateValue, details)
	_ = l.Store.InsertRuntimeEvent(ctx, state.RuntimeEventRecord{
		RuntimeID:   runtimeID,
		ExecutionID: contract.CorrelationContext.ExecutionId,
		EventType:   "runtime.launched",
		Payload:     mustJSON(event),
	})
	if l.Emitter != nil {
		_ = l.Emitter.EmitLifecycle(ctx, event, envelope)
	}
	if l.Fanout != nil {
		l.Fanout.Publish(event)
	}
}

func mustJSON(value any) json.RawMessage {
	if value == nil {
		return nil
	}
	body, _ := json.Marshal(value)
	return body
}
