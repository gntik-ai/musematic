package metrics

import (
	"context"

	"go.opentelemetry.io/otel"
	"go.opentelemetry.io/otel/attribute"
	"go.opentelemetry.io/otel/metric"
)

type Metrics struct {
	simulationCreations    metric.Int64Counter
	simulationTerminations metric.Int64Counter
	simulationDuration     metric.Float64Histogram
	simulationStatus       metric.Int64Gauge
	artifactsCollected     metric.Int64Counter
	artifactsBytes         metric.Int64Counter
	ateSessions            metric.Int64Counter
	ateScenarios           metric.Int64Counter
}

func New() *Metrics {
	meter := otel.GetMeterProvider().Meter("simulation-controller")
	simulationCreations, _ := meter.Int64Counter("simulation_creations_total")
	simulationTerminations, _ := meter.Int64Counter("simulation_terminations_total")
	simulationDuration, _ := meter.Float64Histogram("simulation_duration_seconds")
	simulationStatus, _ := meter.Int64Gauge("simulation_status_current")
	artifactsCollected, _ := meter.Int64Counter("artifacts_collected_total")
	artifactsBytes, _ := meter.Int64Counter("artifacts_bytes_total")
	ateSessions, _ := meter.Int64Counter("ate_sessions_total")
	ateScenarios, _ := meter.Int64Counter("ate_scenarios_total")

	return &Metrics{
		simulationCreations:    simulationCreations,
		simulationTerminations: simulationTerminations,
		simulationDuration:     simulationDuration,
		simulationStatus:       simulationStatus,
		artifactsCollected:     artifactsCollected,
		artifactsBytes:         artifactsBytes,
		ateSessions:            ateSessions,
		ateScenarios:           ateScenarios,
	}
}

func (m *Metrics) RecordSimulationCreated(ctx context.Context) {
	if m == nil {
		return
	}
	m.simulationCreations.Add(ctx, 1)
}

func (m *Metrics) RecordSimulationTermination(ctx context.Context, reason string) {
	if m == nil {
		return
	}
	m.simulationTerminations.Add(ctx, 1, metric.WithAttributes(attribute.String("reason", reason)))
}

func (m *Metrics) RecordSimulationDuration(ctx context.Context, seconds float64) {
	if m == nil {
		return
	}
	m.simulationDuration.Record(ctx, seconds)
}

func (m *Metrics) RecordSimulationStatus(ctx context.Context, status string, value int64) {
	if m == nil {
		return
	}
	m.simulationStatus.Record(ctx, value, metric.WithAttributes(attribute.String("status", status)))
}

func (m *Metrics) RecordArtifactsCollected(ctx context.Context, count int64) {
	if m == nil {
		return
	}
	m.artifactsCollected.Add(ctx, count)
}

func (m *Metrics) RecordArtifactsBytes(ctx context.Context, count int64) {
	if m == nil {
		return
	}
	m.artifactsBytes.Add(ctx, count)
}

func (m *Metrics) RecordATESession(ctx context.Context) {
	if m == nil {
		return
	}
	m.ateSessions.Add(ctx, 1)
}

func (m *Metrics) RecordATEScenario(ctx context.Context, outcome string) {
	if m == nil {
		return
	}
	m.ateScenarios.Add(ctx, 1, metric.WithAttributes(attribute.String("outcome", outcome)))
}
