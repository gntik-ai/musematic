package metrics

import (
	"context"

	"go.opentelemetry.io/otel"
	"go.opentelemetry.io/otel/attribute"
	"go.opentelemetry.io/otel/metric"
)

type Metrics struct {
	budgetDecrements     metric.Int64Counter
	budgetExhaustions    metric.Int64Counter
	budgetCheckDuration  metric.Float64Histogram
	modeSelections       metric.Int64Counter
	totBranches          metric.Int64Counter
	correctionIterations metric.Int64Counter
	correctionCost       metric.Float64Counter
	correctionFailures   metric.Int64Counter
	traceEvents          metric.Int64Counter
	traceDropped         metric.Int64Counter
}

func New() *Metrics {
	meter := otel.GetMeterProvider().Meter("reasoning-engine")
	budgetDecrements, _ := meter.Int64Counter("budget_decrements_total")
	budgetExhaustions, _ := meter.Int64Counter("budget_exhaustion_total")
	budgetCheckDuration, _ := meter.Float64Histogram("budget_check_duration_seconds")
	modeSelections, _ := meter.Int64Counter("mode_selections_total")
	totBranches, _ := meter.Int64Counter("tot_branches_total")
	correctionIterations, _ := meter.Int64Counter("correction_iterations_total")
	correctionCost, _ := meter.Float64Counter("correction_cost_per_loop")
	correctionFailures, _ := meter.Int64Counter("correction_nonconvergence_total")
	traceEvents, _ := meter.Int64Counter("trace_events_total")
	traceDropped, _ := meter.Int64Counter("trace_dropped_total")

	return &Metrics{
		budgetDecrements:     budgetDecrements,
		budgetExhaustions:    budgetExhaustions,
		budgetCheckDuration:  budgetCheckDuration,
		modeSelections:       modeSelections,
		totBranches:          totBranches,
		correctionIterations: correctionIterations,
		correctionCost:       correctionCost,
		correctionFailures:   correctionFailures,
		traceEvents:          traceEvents,
		traceDropped:         traceDropped,
	}
}

func (m *Metrics) RecordBudgetDecrement(ctx context.Context, dimension string) {
	if m == nil {
		return
	}
	m.budgetDecrements.Add(ctx, 1, metric.WithAttributes(attribute.String("dimension", dimension)))
}

func (m *Metrics) RecordBudgetExhaustion(ctx context.Context, dimension string) {
	if m == nil {
		return
	}
	m.budgetExhaustions.Add(ctx, 1, metric.WithAttributes(attribute.String("dimension", dimension)))
}

func (m *Metrics) RecordBudgetCheckDuration(ctx context.Context, seconds float64) {
	if m == nil {
		return
	}
	m.budgetCheckDuration.Record(ctx, seconds)
}

func (m *Metrics) RecordModeSelection(ctx context.Context, mode string) {
	if m == nil {
		return
	}
	m.modeSelections.Add(ctx, 1, metric.WithAttributes(attribute.String("mode", mode)))
}

func (m *Metrics) RecordToTBranch(ctx context.Context, status string) {
	if m == nil {
		return
	}
	m.totBranches.Add(ctx, 1, metric.WithAttributes(attribute.String("status", status)))
}

func (m *Metrics) RecordCorrectionIteration(ctx context.Context, outcome string) {
	if m == nil {
		return
	}
	m.correctionIterations.Add(ctx, 1, metric.WithAttributes(attribute.String("outcome", outcome)))
}

func (m *Metrics) RecordCorrectionCost(ctx context.Context, amount float64) {
	if m == nil {
		return
	}
	m.correctionCost.Add(ctx, amount)
}

func (m *Metrics) RecordCorrectionNonConvergence(ctx context.Context, outcome string) {
	if m == nil {
		return
	}
	m.correctionFailures.Add(ctx, 1, metric.WithAttributes(attribute.String("outcome", outcome)))
}

func (m *Metrics) RecordTraceEvent(ctx context.Context) {
	if m == nil {
		return
	}
	m.traceEvents.Add(ctx, 1)
}

func (m *Metrics) RecordTraceDropped(ctx context.Context) {
	if m == nil {
		return
	}
	m.traceDropped.Add(ctx, 1)
}
