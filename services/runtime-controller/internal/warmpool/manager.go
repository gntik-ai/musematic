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
	store Store
}

func NewManager(store ...Store) *Manager {
	manager := &Manager{ready: map[string][]string{}}
	if len(store) > 0 {
		manager.store = store[0]
	}
	return manager
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

func (m *Manager) RemoveReadyPod(workspaceID string, agentType string, podName string) {
	m.mu.Lock()
	defer m.mu.Unlock()
	k := key(workspaceID, agentType)
	queue := m.ready[k]
	next := make([]string, 0, len(queue))
	for _, existing := range queue {
		if existing != podName {
			next = append(next, existing)
		}
	}
	if len(next) == 0 {
		delete(m.ready, k)
		return
	}
	m.ready[k] = next
}

func (m *Manager) Dispatch(ctx context.Context, workspaceID string, agentType string, runtimeID uuid.UUID) (string, bool, error) {
	m.mu.Lock()
	defer m.mu.Unlock()
	k := key(workspaceID, agentType)
	queue := m.ready[k]
	if len(queue) == 0 {
		return "", false, nil
	}
	podName := queue[0]
	if len(queue) == 1 {
		delete(m.ready, k)
	} else {
		m.ready[k] = queue[1:]
	}
	if m.store != nil {
		if err := m.store.UpdateWarmPoolPodStatus(ctx, podName, "dispatched", &runtimeID); err != nil {
			return "", false, err
		}
	}
	return podName, true, nil
}

func (m *Manager) Count(workspaceID string, agentType string) int {
	m.mu.Lock()
	defer m.mu.Unlock()
	return len(m.ready[key(workspaceID, agentType)])
}
