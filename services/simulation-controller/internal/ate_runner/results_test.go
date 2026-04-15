package ate_runner

import (
	"context"
	"encoding/json"
	"errors"
	"io"
	"log/slog"
	"testing"
	"time"

	simulationv1 "github.com/musematic/simulation-controller/api/grpc/v1"
	"github.com/musematic/simulation-controller/internal/event_streamer"
	"github.com/musematic/simulation-controller/internal/sim_manager"
	"github.com/musematic/simulation-controller/pkg/metrics"
	"github.com/musematic/simulation-controller/pkg/persistence"
	"github.com/stretchr/testify/require"
	corev1 "k8s.io/api/core/v1"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	"k8s.io/apimachinery/pkg/runtime"
	"k8s.io/client-go/kubernetes/fake"
	k8stesting "k8s.io/client-go/testing"
)

type runnerStore struct {
	simulations     []persistence.SimulationRecord
	sessions        []persistence.ATESessionRecord
	results         []persistence.ATEResultRecord
	reportKey       string
	insertSimErr    error
	insertATEErr    error
	insertResultErr error
	updateStatusErr error
	updateReportErr error
}

func (r *runnerStore) InsertSimulation(_ context.Context, record persistence.SimulationRecord) error {
	if r.insertSimErr != nil {
		return r.insertSimErr
	}
	r.simulations = append(r.simulations, record)
	return nil
}

func (r *runnerStore) UpdateSimulationStatus(context.Context, string, persistence.SimulationStatusUpdate) error {
	return r.updateStatusErr
}

func (r *runnerStore) InsertATESession(_ context.Context, record persistence.ATESessionRecord) error {
	if r.insertATEErr != nil {
		return r.insertATEErr
	}
	r.sessions = append(r.sessions, record)
	return nil
}

func (r *runnerStore) InsertATEResult(_ context.Context, record persistence.ATEResultRecord) error {
	if r.insertResultErr != nil {
		return r.insertResultErr
	}
	r.results = append(r.results, record)
	return nil
}

func (r *runnerStore) UpdateATEReport(_ context.Context, _ string, objectKey string, _ time.Time) error {
	if r.updateReportErr != nil {
		return r.updateReportErr
	}
	r.reportKey = objectKey
	return nil
}

type capturingManager struct {
	specs []sim_manager.SimulationPodSpec
	pod   *corev1.Pod
	err   error
}

func (c *capturingManager) CreatePod(_ context.Context, spec sim_manager.SimulationPodSpec) (*corev1.Pod, error) {
	if c.err != nil {
		return nil, c.err
	}
	c.specs = append(c.specs, spec)
	pod, err := sim_manager.BuildPod(spec, sim_manager.DefaultNamespace, sim_manager.DefaultBucket, sim_manager.DefaultMaxDurationSec)
	if err != nil {
		return nil, err
	}
	c.pod = pod
	return pod, nil
}

func (c *capturingManager) DeletePod(context.Context, string) error             { return nil }
func (c *capturingManager) GetPodPhase(context.Context, string) (string, error) { return "", nil }
func (c *capturingManager) EnsureNetworkPolicy(context.Context) error           { return nil }

type recordingUploader struct {
	key      string
	payload  []byte
	metadata map[string]string
	err      error
}

func (r *recordingUploader) Upload(_ context.Context, key string, data []byte, metadata map[string]string) error {
	if r.err != nil {
		return r.err
	}
	r.key = key
	r.payload = append([]byte(nil), data...)
	r.metadata = metadata
	return nil
}

type recordingAggregator struct {
	called chan struct{}
	err    error
}

func (r *recordingAggregator) Run(context.Context, AggregationRequest) error {
	if r.called != nil {
		close(r.called)
	}
	return r.err
}

func TestBuildATEConfigMapSerializesScenarioData(t *testing.T) {
	t.Parallel()

	configMap, err := BuildATEConfigMap(sim_manager.DefaultNamespace, "session-1", []*simulationv1.ATEScenario{{
		ScenarioId:   "scenario-1",
		Name:         "happy path",
		ScorerConfig: `{"threshold":0.9}`,
	}}, []string{"dataset/a.json"})
	require.NoError(t, err)

	require.Equal(t, "ate-session-1", configMap.Name)
	require.Contains(t, configMap.Data["scenarios.json"], "scenario-1")
	require.Contains(t, configMap.Data["dataset_refs.json"], "dataset/a.json")
}

func TestRunnerStartCreatesConfigMapAndATEPod(t *testing.T) {
	t.Parallel()

	client := fake.NewSimpleClientset()
	store := &runnerStore{}
	manager := &capturingManager{}
	registry := sim_manager.NewStateRegistry()
	runner := &Runner{
		Client:    client,
		Namespace: sim_manager.DefaultNamespace,
		Bucket:    sim_manager.DefaultBucket,
		Manager:   manager,
		Store:     store,
		Registry:  registry,
		Logger:    slog.New(slog.NewTextHandler(io.Discard, nil)),
		Now: func() time.Time {
			return time.Date(2026, 4, 10, 12, 0, 0, 0, time.UTC)
		},
		NewID: func() string { return "sim-generated" },
	}

	handle, err := runner.Start(context.Background(), ATERequest{
		SessionID: "session-1",
		AgentID:   "agent-1",
		Config: &simulationv1.SimulationConfig{
			AgentImage:         "busybox:latest",
			MaxDurationSeconds: 60,
		},
		Scenarios: []*simulationv1.ATEScenario{{ScenarioId: "scenario-1", Name: "one"}},
	})
	require.NoError(t, err)
	require.Equal(t, "session-1", handle.GetSessionId())
	require.Equal(t, "sim-generated", handle.GetSimulationId())

	configMap, err := client.CoreV1().ConfigMaps(sim_manager.DefaultNamespace).Get(context.Background(), "ate-session-1", metav1.GetOptions{})
	require.NoError(t, err)
	require.Contains(t, configMap.Data["scenarios.json"], "scenario-1")

	require.Len(t, manager.specs, 1)
	require.Equal(t, "ate-session-1", manager.specs[0].ATEConfigMapName)
	require.NotNil(t, manager.pod)

	var foundMount bool
	for _, mount := range manager.pod.Spec.Containers[0].VolumeMounts {
		if mount.Name == "ate-config" && mount.MountPath == "/ate" {
			foundMount = true
		}
	}
	require.True(t, foundMount)
	require.Len(t, store.simulations, 1)
	require.Len(t, store.sessions, 1)

	state, ok := registry.Get("sim-generated")
	require.True(t, ok)
	require.Equal(t, "CREATING", state.Status)
}

func TestRunnerStartErrorBranchesAndAggregator(t *testing.T) {
	t.Parallel()

	_, err := (*Runner)(nil).Start(context.Background(), ATERequest{})
	require.ErrorIs(t, err, persistence.ErrNotFound)
	_, err = (&Runner{}).Start(context.Background(), ATERequest{})
	require.ErrorIs(t, err, persistence.ErrNotFound)

	baseReq := ATERequest{
		SessionID: "session-1",
		AgentID:   "agent-1",
		Config:    &simulationv1.SimulationConfig{AgentImage: "busybox:latest"},
		Scenarios: []*simulationv1.ATEScenario{{ScenarioId: "scenario-1"}},
	}

	client := fake.NewSimpleClientset(&corev1.ConfigMap{ObjectMeta: metav1.ObjectMeta{Name: "ate-session-1", Namespace: sim_manager.DefaultNamespace}})
	_, err = (&Runner{
		Client:    client,
		Namespace: sim_manager.DefaultNamespace,
		Manager:   &capturingManager{},
		Store:     &runnerStore{},
	}).Start(context.Background(), baseReq)
	require.Error(t, err)

	insertSimErr := errors.New("insert simulation failed")
	_, err = (&Runner{
		Client:    fake.NewSimpleClientset(),
		Namespace: sim_manager.DefaultNamespace,
		Manager:   &capturingManager{},
		Store:     &runnerStore{insertSimErr: insertSimErr},
	}).Start(context.Background(), baseReq)
	require.ErrorIs(t, err, insertSimErr)

	insertATEErr := errors.New("insert ate failed")
	_, err = (&Runner{
		Client:    fake.NewSimpleClientset(),
		Namespace: sim_manager.DefaultNamespace,
		Manager:   &capturingManager{},
		Store:     &runnerStore{insertATEErr: insertATEErr},
	}).Start(context.Background(), baseReq)
	require.ErrorIs(t, err, insertATEErr)

	createErr := errors.New("create pod failed")
	store := &runnerStore{}
	_, err = (&Runner{
		Client:    fake.NewSimpleClientset(),
		Namespace: sim_manager.DefaultNamespace,
		Manager:   &capturingManager{err: createErr},
		Store:     store,
	}).Start(context.Background(), baseReq)
	require.ErrorIs(t, err, createErr)

	called := make(chan struct{})
	_, err = (&Runner{
		Client:    fake.NewSimpleClientset(),
		Namespace: sim_manager.DefaultNamespace,
		Bucket:    sim_manager.DefaultBucket,
		Manager:   &capturingManager{},
		Store:     &runnerStore{},
		Aggregator: &recordingAggregator{
			called: called,
			err:    errors.New("aggregate failed"),
		},
		Logger: slog.New(slog.NewTextHandler(io.Discard, nil)),
		NewID:  func() string { return "sim-aggregator" },
	}).Start(context.Background(), baseReq)
	require.NoError(t, err)
	require.Eventually(t, func() bool {
		select {
		case <-called:
			return true
		default:
			return false
		}
	}, time.Second, 10*time.Millisecond)
}

func TestResultsAggregatorGeneratesATEReport(t *testing.T) {
	t.Parallel()

	fanout := event_streamer.NewFanoutRegistry(10)
	store := &runnerStore{}
	uploader := &recordingUploader{}
	aggregator := &ResultsAggregator{
		Fanout:   fanout,
		Store:    store,
		Uploader: uploader,
		Metrics:  metrics.New(),
	}

	done := make(chan error, 1)
	go func() {
		done <- aggregator.Run(context.Background(), AggregationRequest{
			SimulationID: "sim-1",
			SessionID:    "session-1",
			AgentID:      "agent-1",
			ExpectedScenarios: []*simulationv1.ATEScenario{
				{ScenarioId: "scenario-1"},
				{ScenarioId: "scenario-2"},
			},
		})
	}()
	time.Sleep(20 * time.Millisecond)

	fanout.Publish("sim-1", &simulationv1.SimulationEvent{
		SimulationId: "sim-1",
		EventType:    "ATE_SCENARIO_COMPLETED",
		Simulation:   true,
		Metadata: map[string]string{
			"scenario_id":      "scenario-1",
			"passed":           "true",
			"quality_score":    "0.98",
			"latency_ms":       "120",
			"cost":             "0.02",
			"safety_compliant": "true",
		},
	})
	fanout.Publish("sim-1", &simulationv1.SimulationEvent{
		SimulationId: "sim-1",
		EventType:    "ATE_SCENARIO_COMPLETED",
		Simulation:   true,
		Metadata: map[string]string{
			"scenario_id":      "scenario-2",
			"passed":           "false",
			"quality_score":    "0.61",
			"latency_ms":       "250",
			"cost":             "0.11",
			"safety_compliant": "false",
			"error":            "threshold not met",
		},
	})

	require.NoError(t, <-done)
	require.Len(t, store.results, 2)
	require.Equal(t, "sim-1/ate-report.json", uploader.key)
	require.Equal(t, "sim-1/ate-report.json", store.reportKey)

	var report map[string]any
	require.NoError(t, json.Unmarshal(uploader.payload, &report))
	require.Equal(t, "session-1", report["session_id"])
	summary := report["summary"].(map[string]any)
	require.EqualValues(t, 2, summary["total"])
	require.EqualValues(t, 1, summary["passed"])
	require.EqualValues(t, 1, summary["failed"])
}

func TestResultsAggregatorErrorAndExitBranches(t *testing.T) {
	t.Parallel()

	require.NoError(t, (*ResultsAggregator)(nil).Run(context.Background(), AggregationRequest{}))
	require.NoError(t, (&ResultsAggregator{}).Run(context.Background(), AggregationRequest{}))

	ctx, cancel := context.WithCancel(context.Background())
	cancel()
	err := (&ResultsAggregator{Fanout: event_streamer.NewFanoutRegistry(1)}).Run(ctx, AggregationRequest{SimulationID: "sim-1"})
	require.ErrorIs(t, err, context.Canceled)

	fanout := event_streamer.NewFanoutRegistry(1)
	storeErr := errors.New("store failed")
	done := make(chan error, 1)
	go func() {
		done <- (&ResultsAggregator{
			Fanout: fanout,
			Store:  &runnerStore{insertResultErr: storeErr},
		}).Run(context.Background(), AggregationRequest{
			SimulationID:      "sim-store",
			SessionID:         "session-1",
			ExpectedScenarios: []*simulationv1.ATEScenario{{ScenarioId: "scenario-1"}},
		})
	}()
	require.Eventually(t, func() bool {
		return fanout.SubscriberCount("sim-store") == 1
	}, time.Second, 10*time.Millisecond)
	fanout.Publish("sim-store", &simulationv1.SimulationEvent{
		EventType: "ATE_SCENARIO_COMPLETED",
		Metadata:  map[string]string{"scenario_id": "scenario-1"},
	})
	require.ErrorIs(t, <-done, storeErr)

	for _, tc := range []struct {
		name     string
		uploader *recordingUploader
		store    *runnerStore
		wantErr  error
	}{
		{name: "upload", uploader: &recordingUploader{err: errors.New("upload failed")}, store: &runnerStore{}},
		{name: "update", uploader: &recordingUploader{}, store: &runnerStore{updateReportErr: errors.New("update failed")}},
	} {
		t.Run(tc.name, func(t *testing.T) {
			fanout := event_streamer.NewFanoutRegistry(1)
			done := make(chan error, 1)
			go func() {
				done <- (&ResultsAggregator{
					Fanout:   fanout,
					Store:    tc.store,
					Uploader: tc.uploader,
				}).Run(context.Background(), AggregationRequest{
					SimulationID:      "sim-" + tc.name,
					SessionID:         "session-1",
					ExpectedScenarios: []*simulationv1.ATEScenario{{ScenarioId: "scenario-1"}},
				})
			}()
			require.Eventually(t, func() bool {
				return fanout.SubscriberCount("sim-"+tc.name) == 1
			}, time.Second, 10*time.Millisecond)
			fanout.Publish("sim-"+tc.name, &simulationv1.SimulationEvent{
				EventType: "ATE_SCENARIO_COMPLETED",
				Metadata: map[string]string{
					"scenario_id": "scenario-1",
					"passed":      "true",
				},
			})
			require.Error(t, <-done)
		})
	}

	closingFanout := event_streamer.NewFanoutRegistry(1)
	done = make(chan error, 1)
	go func() {
		done <- (&ResultsAggregator{Fanout: closingFanout}).Run(context.Background(), AggregationRequest{SimulationID: "sim-close"})
	}()
	require.Eventually(t, func() bool {
		return closingFanout.SubscriberCount("sim-close") == 1
	}, time.Second, 10*time.Millisecond)
	closingFanout.Close("sim-close")
	require.NoError(t, <-done)
}

func TestATEHelpersCoverDeleteCleanupAndParsers(t *testing.T) {
	t.Parallel()

	client := fake.NewSimpleClientset()
	_, err := CreateATEConfigMap(context.Background(), client, sim_manager.DefaultNamespace, "session-1", nil, nil)
	require.NoError(t, err)
	require.NoError(t, (&Runner{Client: client, Namespace: sim_manager.DefaultNamespace}).Cleanup(context.Background(), "session-1"))
	require.NoError(t, DeleteATEConfigMap(context.Background(), client, sim_manager.DefaultNamespace, "missing"))

	errorClient := fake.NewSimpleClientset(&corev1.ConfigMap{ObjectMeta: metav1.ObjectMeta{Name: "ate-session-err", Namespace: sim_manager.DefaultNamespace}})
	deleteErr := errors.New("delete failed")
	errorClient.PrependReactor("delete", "configmaps", func(k8stesting.Action) (bool, runtime.Object, error) {
		return true, nil, deleteErr
	})
	require.ErrorIs(t, DeleteATEConfigMap(context.Background(), errorClient, sim_manager.DefaultNamespace, "session-err"), deleteErr)

	runner := &Runner{}
	require.NoError(t, runner.Cleanup(context.Background(), "session-1"))
	require.NoError(t, (*Runner)(nil).Cleanup(context.Background(), "session-1"))
	require.EqualValues(t, 1, safeInt32(1))
	require.EqualValues(t, int32(2147483647), safeInt32(1<<62))
	require.EqualValues(t, int32(-2147483648), safeInt32(-1<<62))

	require.Nil(t, parseBoolPtr(""))
	require.False(t, *parseBoolPtr("false"))
	require.Nil(t, parseFloat(""))
	require.Nil(t, parseFloat("bad"))
	require.Nil(t, parseInt32(""))
	require.Nil(t, parseInt32("bad"))

	report := buildReport(AggregationRequest{
		SessionID: "session-1",
		AgentID:   "agent-1",
		ExpectedScenarios: []*simulationv1.ATEScenario{
			{ScenarioId: "scenario-1"},
			{ScenarioId: "missing"},
		},
	}, map[string]scenarioReport{
		"scenario-1": {ScenarioID: "scenario-1", Passed: true},
	})
	require.EqualValues(t, 1, report.Summary.Total)
	require.EqualValues(t, 1, report.Summary.Passed)
}
