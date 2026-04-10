package ate_runner

import (
	"context"
	"log/slog"
	"time"

	"github.com/google/uuid"
	simulationv1 "github.com/musematic/simulation-controller/api/grpc/v1"
	"github.com/musematic/simulation-controller/internal/sim_manager"
	"github.com/musematic/simulation-controller/pkg/persistence"
	"google.golang.org/protobuf/encoding/protojson"
	"google.golang.org/protobuf/types/known/timestamppb"
	"k8s.io/client-go/kubernetes"
)

type ATERunner interface {
	Start(ctx context.Context, req ATERequest) (*simulationv1.ATEHandle, error)
	Cleanup(ctx context.Context, sessionID string) error
}

type resultsStarter interface {
	Run(ctx context.Context, req AggregationRequest) error
}

type store interface {
	InsertSimulation(ctx context.Context, record persistence.SimulationRecord) error
	UpdateSimulationStatus(ctx context.Context, simulationID string, update persistence.SimulationStatusUpdate) error
	InsertATESession(ctx context.Context, record persistence.ATESessionRecord) error
}

type ATERequest struct {
	SessionID   string
	AgentID     string
	Config      *simulationv1.SimulationConfig
	Scenarios   []*simulationv1.ATEScenario
	DatasetRefs []string
}

type Runner struct {
	Client     kubernetes.Interface
	Namespace  string
	Bucket     string
	Manager    sim_manager.Manager
	Store      store
	Registry   *sim_manager.StateRegistry
	Aggregator resultsStarter
	Logger     *slog.Logger
	Now        func() time.Time
	NewID      func() string
}

func (r *Runner) Start(ctx context.Context, req ATERequest) (*simulationv1.ATEHandle, error) {
	if r == nil || r.Client == nil || r.Manager == nil || r.Store == nil {
		return nil, persistence.ErrNotFound
	}

	now := time.Now().UTC()
	if r.Now != nil {
		now = r.Now().UTC()
	}
	newID := uuid.NewString
	if r.NewID != nil {
		newID = r.NewID
	}
	simulationID := newID()

	if _, err := CreateATEConfigMap(ctx, r.Client, r.Namespace, req.SessionID, req.Scenarios, req.DatasetRefs); err != nil {
		return nil, err
	}

	configJSON, err := protojson.Marshal(req.Config)
	if err != nil {
		return nil, err
	}
	if err := r.Store.InsertSimulation(ctx, persistence.SimulationRecord{
		SimulationID:       simulationID,
		AgentImage:         req.Config.GetAgentImage(),
		AgentConfigJSON:    configJSON,
		Status:             "CREATING",
		Namespace:          r.Namespace,
		CPURequest:         req.Config.GetCpuRequest(),
		MemoryRequest:      req.Config.GetMemoryRequest(),
		MaxDurationSeconds: req.Config.GetMaxDurationSeconds(),
		CreatedAt:          now,
	}); err != nil {
		return nil, err
	}

	scenariosJSON, err := protojson.Marshal(&simulationv1.CreateATERequest{
		SessionId: req.SessionID,
		AgentId:   req.AgentID,
		Config:    req.Config,
		Scenarios: req.Scenarios,
	})
	if err != nil {
		return nil, err
	}
	if err := r.Store.InsertATESession(ctx, persistence.ATESessionRecord{
		SessionID:     req.SessionID,
		SimulationID:  simulationID,
		AgentID:       req.AgentID,
		ScenariosJSON: scenariosJSON,
		CreatedAt:     now,
	}); err != nil {
		return nil, err
	}

	pod, err := r.Manager.CreatePod(ctx, sim_manager.SimulationPodSpec{
		SimulationID:       simulationID,
		AgentImage:         req.Config.GetAgentImage(),
		AgentEnv:           req.Config.GetAgentEnv(),
		CPURequest:         req.Config.GetCpuRequest(),
		MemoryRequest:      req.Config.GetMemoryRequest(),
		MaxDurationSeconds: req.Config.GetMaxDurationSeconds(),
		Namespace:          r.Namespace,
		Bucket:             r.Bucket,
		ATEConfigMapName:   ateConfigMapName(req.SessionID),
		ATESessionID:       req.SessionID,
	})
	if err != nil {
		message := err.Error()
		_ = r.Store.UpdateSimulationStatus(ctx, simulationID, persistence.SimulationStatusUpdate{
			Status:       "FAILED",
			ErrorMessage: &message,
		})
		_ = DeleteATEConfigMap(ctx, r.Client, r.Namespace, req.SessionID)
		return nil, err
	}

	_ = r.Store.UpdateSimulationStatus(ctx, simulationID, persistence.SimulationStatusUpdate{
		Status:  "CREATING",
		PodName: pod.Name,
	})

	if r.Registry != nil {
		r.Registry.Register(sim_manager.SimulationState{
			SimulationID: simulationID,
			Status:       "CREATING",
			PodName:      pod.Name,
			CreatedAt:    &now,
			ResourceUsage: sim_manager.ResourceUsage{
				CPURequest:    req.Config.GetCpuRequest(),
				MemoryRequest: req.Config.GetMemoryRequest(),
				CPULimit:      req.Config.GetCpuRequest(),
				MemoryLimit:   req.Config.GetMemoryRequest(),
			},
		})
	}

	if r.Aggregator != nil {
		go func() {
			if err := r.Aggregator.Run(context.Background(), AggregationRequest{
				SimulationID:      simulationID,
				SessionID:         req.SessionID,
				AgentID:           req.AgentID,
				ExpectedScenarios: req.Scenarios,
			}); err != nil && r.Logger != nil {
				r.Logger.Error("ate aggregation failed", "error", err, "simulation_id", simulationID)
			}
		}()
	}

	return &simulationv1.ATEHandle{
		SessionId:     req.SessionID,
		SimulationId:  simulationID,
		Status:        "PROVISIONING",
		ScenarioCount: int32(len(req.Scenarios)),
		CreatedAt:     timestamppb.New(now),
	}, nil
}

func (r *Runner) Cleanup(ctx context.Context, sessionID string) error {
	if r == nil {
		return nil
	}
	return DeleteATEConfigMap(ctx, r.Client, r.Namespace, sessionID)
}
