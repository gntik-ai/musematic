package warmpool

import (
	"context"
	"sync"

	"github.com/andrea-mucci/musematic/services/runtime-controller/internal/state"
	"github.com/google/uuid"
)

type Store interface {
	ListWarmPoolPodsByStatus(context.Context, string) ([]state.WarmPoolPod, error)
	UpdateWarmPoolPodStatus(context.Context, string, string, *uuid.UUID) error
}

type Manager struct {
	mu    sync.Mutex
	ready map[string][]string
}

func NewManager() *Manager {
	return &Manager{ready: map[string][]string{}}
}

func key(workspaceID string, agentType string) string {
	return workspaceID + "/" + agentType
}

func (m *Manager) LoadFromDB(ctx context.Context, store interface {
	ListWarmPoolPodsByStatus(context.Context, string) ([]state.WarmPoolPod, error)
}) error {
	pods, err := store.ListWarmPoolPodsByStatus(ctx, "ready")
	if err != nil {
		return err
	}
	m.mu.Lock()
	defer m.mu.Unlock()
	for _, pod := range pods {
		k := key(pod.WorkspaceID, pod.AgentType)
		m.ready[k] = append(m.ready[k], pod.PodName)
	}
	return nil
}

func (m *Manager) RegisterReadyPod(workspaceID string, agentType string, podName string) {
	m.mu.Lock()
	defer m.mu.Unlock()
	k := key(workspaceID, agentType)
	m.ready[k] = append(m.ready[k], podName)
}

func (m *Manager) Dispatch(workspaceID string, agentType string) (string, bool) {
	m.mu.Lock()
	defer m.mu.Unlock()
	k := key(workspaceID, agentType)
	queue := m.ready[k]
	if len(queue) == 0 {
		return "", false
	}
	podName := queue[0]
	if len(queue) == 1 {
		delete(m.ready, k)
	} else {
		m.ready[k] = queue[1:]
	}
	return podName, true
}

func (m *Manager) Count(workspaceID string, agentType string) int {
	m.mu.Lock()
	defer m.mu.Unlock()
	return len(m.ready[key(workspaceID, agentType)])
}
