package sim_manager

import (
	"context"

	corev1 "k8s.io/api/core/v1"
)

const (
	DefaultNamespace      = "platform-simulation"
	DefaultBucket         = "simulation-artifacts"
	DefaultCPURequest     = "500m"
	DefaultMemoryRequest  = "512Mi"
	DefaultMaxDurationSec = int32(3600)

	SimulationLabelKey   = "simulation"
	SimulationIDLabelKey = "simulation-id"
)

type Manager interface {
	CreatePod(ctx context.Context, spec SimulationPodSpec) (*corev1.Pod, error)
	DeletePod(ctx context.Context, podName string) error
	GetPodPhase(ctx context.Context, podName string) (string, error)
	EnsureNetworkPolicy(ctx context.Context) error
}

type SimulationPodSpec struct {
	SimulationID       string
	AgentImage         string
	AgentEnv           map[string]string
	CPURequest         string
	MemoryRequest      string
	CPULimit           string
	MemoryLimit        string
	MaxDurationSeconds int32
	Namespace          string
	Bucket             string
	ATEConfigMapName   string
	ATESessionID       string
}

type ResourceUsage struct {
	CPURequest    string
	MemoryRequest string
	CPULimit      string
	MemoryLimit   string
}
