package metrics

import (
	"fmt"
	"net/http"
	"sync"
	"time"
)

type Registry struct {
	mu                       sync.RWMutex
	launchesTotal            int64
	heartbeatTimeoutsTotal   int64
	activeRuntimes           int64
	launchDurationSeconds    []float64
	reconcileDurationSeconds []float64
}

func NewRegistry() *Registry {
	return &Registry{}
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
	}
}

func writeMetric(w http.ResponseWriter, name string, value float64) {
	_, _ = fmt.Fprintf(w, "# TYPE %s gauge\n%s %g\n", name, name, value)
}

func sum(values []float64) float64 {
	var total float64
	for _, value := range values {
		total += value
	}
	return total
}
