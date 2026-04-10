package sandbox

import (
	"context"
	"fmt"
	"sync"
	"time"

	sandboxv1 "github.com/andrea-mucci/musematic/services/sandbox-manager/api/grpc/v1"
	"github.com/andrea-mucci/musematic/services/sandbox-manager/internal/events"
	"github.com/andrea-mucci/musematic/services/sandbox-manager/internal/state"
	"github.com/andrea-mucci/musematic/services/sandbox-manager/internal/templates"
	"github.com/google/uuid"
	v1 "k8s.io/api/core/v1"
)

var (
	ErrTemplateNotFound = fmt.Errorf("sandbox template not found")
	ErrConcurrentLimit  = fmt.Errorf("max concurrent sandboxes reached")
	ErrSandboxNotFound  = fmt.Errorf("sandbox not found")
	ErrInvalidState     = fmt.Errorf("sandbox state does not allow this operation")
)

type PodController interface {
	CreatePod(context.Context, *v1.Pod) (*v1.Pod, error)
	GetPod(context.Context, string) (*v1.Pod, error)
	ListPodsByLabel(context.Context, string) ([]v1.Pod, error)
	DeletePod(context.Context, string, int64) error
}

type Store interface {
	InsertSandbox(context.Context, state.SandboxRecord) error
	UpdateSandboxState(context.Context, string, string, string, int32, *int64) error
	InsertSandboxEvent(context.Context, state.SandboxEventRecord) error
}

type EventEmitter interface {
	Emit(context.Context, *sandboxv1.SandboxEvent, events.Envelope) error
}

type Entry struct {
	SandboxID       string
	ExecutionID     string
	WorkspaceID     string
	Template        string
	State           sandboxv1.SandboxState
	FailureReason   string
	PodName         string
	PodNamespace    string
	ResourceLimits  *sandboxv1.ResourceLimits
	NetworkEnabled  bool
	TotalSteps      int32
	TotalDurationMS int64
	CreatedAt       time.Time
	ReadyAt         time.Time
	TerminatedAt    time.Time
	LastActivityAt  time.Time
	Correlation     *sandboxv1.CorrelationContext
}

type ManagerConfig struct {
	Namespace      string
	DefaultTimeout time.Duration
	MaxTimeout     time.Duration
	MaxConcurrent  int
	Store          Store
	Pods           PodController
	Emitter        EventEmitter
	ReadyCallback  func(Entry)
}

type Manager struct {
	mu             sync.RWMutex
	namespace      string
	defaultTimeout time.Duration
	maxTimeout     time.Duration
	maxConcurrent  int
	store          Store
	pods           PodController
	emitter        EventEmitter
	readyCallback  func(Entry)
	sandboxes      map[string]*Entry
}

func NewManager(cfg ManagerConfig) *Manager {
	return &Manager{
		namespace:      cfg.Namespace,
		defaultTimeout: cfg.DefaultTimeout,
		maxTimeout:     cfg.MaxTimeout,
		maxConcurrent:  cfg.MaxConcurrent,
		store:          cfg.Store,
		pods:           cfg.Pods,
		emitter:        cfg.Emitter,
		readyCallback:  cfg.ReadyCallback,
		sandboxes:      map[string]*Entry{},
	}
}

func (m *Manager) Create(ctx context.Context, req *sandboxv1.CreateSandboxRequest) (*Entry, error) {
	tmpl, err := templates.Lookup(req.GetTemplateName())
	if err != nil {
		return nil, ErrTemplateNotFound
	}
	if req.GetCorrelation().GetWorkspaceId() == "" || req.GetCorrelation().GetExecutionId() == "" {
		return nil, fmt.Errorf("missing correlation context")
	}

	m.mu.Lock()
	if m.activeCountLocked() >= m.maxConcurrent {
		m.mu.Unlock()
		return nil, ErrConcurrentLimit
	}
	sandboxID := uuid.NewString()
	entry := &Entry{
		SandboxID:      sandboxID,
		ExecutionID:    req.GetCorrelation().GetExecutionId(),
		WorkspaceID:    req.GetCorrelation().GetWorkspaceId(),
		Template:       tmpl.Name,
		State:          sandboxv1.SandboxState_SANDBOX_STATE_CREATING,
		PodName:        fmt.Sprintf("sandbox-%s", shortID(sandboxID)),
		PodNamespace:   m.namespace,
		ResourceLimits: mergeResourceLimits(tmpl.Limits, req.GetResourceOverrides()),
		NetworkEnabled: req.GetNetworkEnabled(),
		CreatedAt:      time.Now().UTC(),
		LastActivityAt: time.Now().UTC(),
		Correlation:    req.GetCorrelation(),
	}
	m.sandboxes[sandboxID] = entry
	m.mu.Unlock()

	pod, err := BuildPodSpec(sandboxID, tmpl, req, m.namespace, m.maxTimeout)
	if err != nil {
		m.removeSandbox(sandboxID)
		return nil, err
	}
	createdPod, err := m.pods.CreatePod(ctx, pod)
	if err != nil {
		m.removeSandbox(sandboxID)
		return nil, err
	}
	entry.PodName = createdPod.Name

	if m.store != nil {
		record := state.SandboxRecord{
			SandboxID:      uuid.MustParse(sandboxID),
			ExecutionID:    entry.ExecutionID,
			WorkspaceID:    entry.WorkspaceID,
			Template:       entry.Template,
			State:          "creating",
			PodName:        entry.PodName,
			PodNamespace:   entry.PodNamespace,
			ResourceLimits: state.MarshalResourceLimits(entry.ResourceLimits),
			NetworkEnabled: entry.NetworkEnabled,
			TotalSteps:     entry.TotalSteps,
			CreatedAt:      entry.CreatedAt,
			UpdatedAt:      entry.CreatedAt,
		}
		if err := m.store.InsertSandbox(ctx, record); err != nil {
			m.removeSandbox(sandboxID)
			return nil, err
		}
	}
	_ = m.emitState(ctx, entry, sandboxv1.SandboxEventType_SANDBOX_EVENT_CREATED, "sandbox.created")
	go m.monitorPod(context.Background(), sandboxID)
	return entry.Copy(), nil
}

func (m *Manager) Get(sandboxID string) (*Entry, error) {
	m.mu.RLock()
	defer m.mu.RUnlock()
	entry, ok := m.sandboxes[sandboxID]
	if !ok {
		return nil, ErrSandboxNotFound
	}
	return entry.Copy(), nil
}

func (m *Manager) List() []Entry {
	m.mu.RLock()
	defer m.mu.RUnlock()
	items := make([]Entry, 0, len(m.sandboxes))
	for _, entry := range m.sandboxes {
		items = append(items, *entry.Copy())
	}
	return items
}

func (m *Manager) RecordStep(sandboxID string, duration time.Duration) (int32, error) {
	m.mu.Lock()
	defer m.mu.Unlock()
	entry, ok := m.sandboxes[sandboxID]
	if !ok {
		return 0, ErrSandboxNotFound
	}
	entry.TotalSteps++
	entry.TotalDurationMS += duration.Milliseconds()
	entry.LastActivityAt = time.Now().UTC()
	if m.store != nil {
		total := entry.TotalDurationMS
		if err := m.store.UpdateSandboxState(context.Background(), sandboxID, stateName(entry.State), entry.FailureReason, entry.TotalSteps, &total); err != nil {
			return 0, err
		}
	}
	return entry.TotalSteps, nil
}

func (m *Manager) HasSandbox(sandboxID string) bool {
	m.mu.RLock()
	defer m.mu.RUnlock()
	_, ok := m.sandboxes[sandboxID]
	return ok
}

func (m *Manager) activeCountLocked() int {
	count := 0
	for _, entry := range m.sandboxes {
		if entry.State != sandboxv1.SandboxState_SANDBOX_STATE_TERMINATED {
			count++
		}
	}
	return count
}

func (m *Manager) removeSandbox(sandboxID string) {
	m.mu.Lock()
	defer m.mu.Unlock()
	delete(m.sandboxes, sandboxID)
}

func (m *Manager) monitorPod(ctx context.Context, sandboxID string) {
	ticker := time.NewTicker(1 * time.Second)
	defer ticker.Stop()
	for {
		select {
		case <-ctx.Done():
			return
		case <-ticker.C:
			entry, err := m.Get(sandboxID)
			if err != nil {
				return
			}
			pod, err := m.pods.GetPod(ctx, entry.PodName)
			if err != nil {
				return
			}
			switch pod.Status.Phase {
			case v1.PodRunning:
				if err := m.Transition(ctx, sandboxID, sandboxv1.SandboxState_SANDBOX_STATE_CREATING, sandboxv1.SandboxState_SANDBOX_STATE_READY, ""); err == nil && m.readyCallback != nil {
					if current, getErr := m.Get(sandboxID); getErr == nil {
						m.readyCallback(*current)
					}
				}
				return
			case v1.PodFailed:
				_ = m.MarkFailed(ctx, sandboxID, "pod failed before ready")
				return
			}
		}
	}
}

func (e *Entry) Copy() *Entry {
	if e == nil {
		return nil
	}
	copy := *e
	if e.ResourceLimits != nil {
		limitsCopy := *e.ResourceLimits
		copy.ResourceLimits = &limitsCopy
	}
	if e.Correlation != nil {
		corrCopy := *e.Correlation
		copy.Correlation = &corrCopy
	}
	return &copy
}

func stateName(value sandboxv1.SandboxState) string {
	switch value {
	case sandboxv1.SandboxState_SANDBOX_STATE_CREATING:
		return "creating"
	case sandboxv1.SandboxState_SANDBOX_STATE_READY:
		return "ready"
	case sandboxv1.SandboxState_SANDBOX_STATE_EXECUTING:
		return "executing"
	case sandboxv1.SandboxState_SANDBOX_STATE_COMPLETED:
		return "completed"
	case sandboxv1.SandboxState_SANDBOX_STATE_FAILED:
		return "failed"
	case sandboxv1.SandboxState_SANDBOX_STATE_TERMINATED:
		return "terminated"
	default:
		return "creating"
	}
}
