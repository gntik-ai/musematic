package metrics

import (
	"fmt"
	"net/http"
	"sort"
	"strings"
	"sync"
	"time"
)

type warmPoolMetricKey struct {
	workspaceID string
	agentType   string
}

type HistogramSnapshot struct {
	Count int
	Sum   float64
}

type Snapshot struct {
	LaunchesTotal            int64
	HeartbeatTimeoutsTotal   int64
	ActiveRuntimes           int64
	LaunchDurationSeconds    []float64
	ReconcileDurationSeconds []float64
	WarmPoolAvailable        map[string]float64
	WarmPoolTarget           map[string]float64
	WarmPoolWarming          map[string]float64
	WarmPoolDispatches       map[string]float64
	ColdStartCount           map[string]float64
	WarmDispatchLatency      map[string]HistogramSnapshot
}

type Registry struct {
	mu                       sync.RWMutex
	launchesTotal            int64
	heartbeatTimeoutsTotal   int64
	activeRuntimes           int64
	launchDurationSeconds    []float64
	reconcileDurationSeconds []float64
	warmPoolAvailable        map[warmPoolMetricKey]float64
	warmPoolTarget           map[warmPoolMetricKey]float64
	warmPoolWarming          map[warmPoolMetricKey]float64
	warmPoolDispatches       map[warmPoolMetricKey]float64
	coldStartCount           map[warmPoolMetricKey]float64
	warmDispatchLatency      map[warmPoolMetricKey][]float64
}

func NewRegistry() *Registry {
	return &Registry{
		warmPoolAvailable:   map[warmPoolMetricKey]float64{},
		warmPoolTarget:      map[warmPoolMetricKey]float64{},
		warmPoolWarming:     map[warmPoolMetricKey]float64{},
		warmPoolDispatches:  map[warmPoolMetricKey]float64{},
		coldStartCount:      map[warmPoolMetricKey]float64{},
		warmDispatchLatency: map[warmPoolMetricKey][]float64{},
	}
}

func (r *Registry) IncLaunches() {
	r.mu.Lock()
	defer r.mu.Unlock()
	r.launchesTotal++
}

func (r *Registry) ObserveLaunchDuration(duration time.Duration) {
	r.mu.Lock()
	defer r.mu.Unlock()
	r.launchDurationSeconds = append(r.launchDurationSeconds, duration.Seconds())
}

func (r *Registry) SetActiveRuntimes(value int64) {
	r.mu.Lock()
	defer r.mu.Unlock()
	r.activeRuntimes = value
}

func (r *Registry) ObserveReconciliationDuration(duration time.Duration) {
	r.mu.Lock()
	defer r.mu.Unlock()
	r.reconcileDurationSeconds = append(r.reconcileDurationSeconds, duration.Seconds())
}

func (r *Registry) IncHeartbeatTimeouts() {
	r.mu.Lock()
	defer r.mu.Unlock()
	r.heartbeatTimeoutsTotal++
}

func (r *Registry) SetWarmPoolAvailable(workspaceID string, agentType string, count float64) {
	r.mu.Lock()
	defer r.mu.Unlock()
	r.warmPoolAvailable[labelKey(workspaceID, agentType)] = count
}

func (r *Registry) SetWarmPoolTarget(workspaceID string, agentType string, count float64) {
	r.mu.Lock()
	defer r.mu.Unlock()
	r.warmPoolTarget[labelKey(workspaceID, agentType)] = count
}

func (r *Registry) SetWarmPoolWarming(workspaceID string, agentType string, count float64) {
	r.mu.Lock()
	defer r.mu.Unlock()
	r.warmPoolWarming[labelKey(workspaceID, agentType)] = count
}

func (r *Registry) IncWarmPoolDispatches(workspaceID string, agentType string) {
	r.mu.Lock()
	defer r.mu.Unlock()
	key := labelKey(workspaceID, agentType)
	r.warmPoolDispatches[key]++
}

func (r *Registry) IncColdStart(workspaceID string, agentType string) {
	r.mu.Lock()
	defer r.mu.Unlock()
	key := labelKey(workspaceID, agentType)
	r.coldStartCount[key]++
}

func (r *Registry) ObserveWarmDispatchLatency(workspaceID string, agentType string, ms float64) {
	r.mu.Lock()
	defer r.mu.Unlock()
	key := labelKey(workspaceID, agentType)
	r.warmDispatchLatency[key] = append(r.warmDispatchLatency[key], ms)
}

func (r *Registry) Snapshot() Snapshot {
	r.mu.RLock()
	defer r.mu.RUnlock()
	return Snapshot{
		LaunchesTotal:            r.launchesTotal,
		HeartbeatTimeoutsTotal:   r.heartbeatTimeoutsTotal,
		ActiveRuntimes:           r.activeRuntimes,
		LaunchDurationSeconds:    append([]float64(nil), r.launchDurationSeconds...),
		ReconcileDurationSeconds: append([]float64(nil), r.reconcileDurationSeconds...),
		WarmPoolAvailable:        cloneGaugeMap(r.warmPoolAvailable),
		WarmPoolTarget:           cloneGaugeMap(r.warmPoolTarget),
		WarmPoolWarming:          cloneGaugeMap(r.warmPoolWarming),
		WarmPoolDispatches:       cloneGaugeMap(r.warmPoolDispatches),
		ColdStartCount:           cloneGaugeMap(r.coldStartCount),
		WarmDispatchLatency:      cloneHistogramMap(r.warmDispatchLatency),
	}
}

func (r *Registry) Handler() http.HandlerFunc {
	return func(w http.ResponseWriter, _ *http.Request) {
		r.mu.RLock()
		defer r.mu.RUnlock()
		w.Header().Set("Content-Type", "text/plain; version=0.0.4")
		writeMetric(w, "runtime_controller_launches_total", float64(r.launchesTotal))
		writeMetric(w, "runtime_controller_launch_duration_seconds", sum(r.launchDurationSeconds))
		writeMetric(w, "runtime_controller_active_runtimes", float64(r.activeRuntimes))
		writeMetric(w, "runtime_controller_reconciliation_cycle_duration_seconds", sum(r.reconcileDurationSeconds))
		writeMetric(w, "runtime_controller_heartbeat_timeouts_total", float64(r.heartbeatTimeoutsTotal))
		writeLabeledMetrics(w, "gauge", "runtime_controller_warm_pool_available", r.warmPoolAvailable)
		writeLabeledMetrics(w, "gauge", "runtime_controller_warm_pool_target", r.warmPoolTarget)
		writeLabeledMetrics(w, "gauge", "runtime_controller_warm_pool_warming", r.warmPoolWarming)
		writeLabeledMetrics(w, "counter", "runtime_controller_warm_pool_dispatches_total", r.warmPoolDispatches)
		writeLabeledMetrics(w, "counter", "runtime_controller_cold_start_count_total", r.coldStartCount)
		writeHistogramMetrics(w, "runtime_controller_warm_dispatch_latency_ms", r.warmDispatchLatency)
	}
}

func labelKey(workspaceID string, agentType string) warmPoolMetricKey {
	return warmPoolMetricKey{workspaceID: workspaceID, agentType: agentType}
}

func cloneGaugeMap(source map[warmPoolMetricKey]float64) map[string]float64 {
	out := make(map[string]float64, len(source))
	for key, value := range source {
		out[key.workspaceID+"/"+key.agentType] = value
	}
	return out
}

func cloneHistogramMap(source map[warmPoolMetricKey][]float64) map[string]HistogramSnapshot {
	out := make(map[string]HistogramSnapshot, len(source))
	for key, values := range source {
		out[key.workspaceID+"/"+key.agentType] = HistogramSnapshot{Count: len(values), Sum: sum(values)}
	}
	return out
}

func writeMetric(w http.ResponseWriter, name string, value float64) {
	_, _ = fmt.Fprintf(w, "# TYPE %s gauge\n%s %g\n", name, name, value)
}

func writeLabeledMetrics(w http.ResponseWriter, metricType string, name string, values map[warmPoolMetricKey]float64) {
	_, _ = fmt.Fprintf(w, "# TYPE %s %s\n", name, metricType)
	for _, key := range sortedKeys(values) {
		_, _ = fmt.Fprintf(
			w,
			"%s{workspace_id=%q,agent_type=%q} %g\n",
			name,
			key.workspaceID,
			key.agentType,
			values[key],
		)
	}
}

func writeHistogramMetrics(w http.ResponseWriter, name string, values map[warmPoolMetricKey][]float64) {
	_, _ = fmt.Fprintf(w, "# TYPE %s histogram\n", name)
	for _, key := range sortedHistogramKeys(values) {
		samples := values[key]
		_, _ = fmt.Fprintf(w, "%s_sum{workspace_id=%q,agent_type=%q} %g\n", name, key.workspaceID, key.agentType, sum(samples))
		_, _ = fmt.Fprintf(w, "%s_count{workspace_id=%q,agent_type=%q} %d\n", name, key.workspaceID, key.agentType, len(samples))
	}
}

func sortedKeys(values map[warmPoolMetricKey]float64) []warmPoolMetricKey {
	keys := make([]warmPoolMetricKey, 0, len(values))
	for key := range values {
		keys = append(keys, key)
	}
	sort.Slice(keys, func(i int, j int) bool {
		left := keys[i].workspaceID + "/" + keys[i].agentType
		right := keys[j].workspaceID + "/" + keys[j].agentType
		return strings.Compare(left, right) < 0
	})
	return keys
}

func sortedHistogramKeys(values map[warmPoolMetricKey][]float64) []warmPoolMetricKey {
	keys := make([]warmPoolMetricKey, 0, len(values))
	for key := range values {
		keys = append(keys, key)
	}
	sort.Slice(keys, func(i int, j int) bool {
		left := keys[i].workspaceID + "/" + keys[i].agentType
		right := keys[j].workspaceID + "/" + keys[j].agentType
		return strings.Compare(left, right) < 0
	})
	return keys
}

func sum(values []float64) float64 {
	var total float64
	for _, value := range values {
		total += value
	}
	return total
}
