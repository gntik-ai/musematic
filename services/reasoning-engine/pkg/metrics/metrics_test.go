package metrics

import (
	"context"
	"testing"
)

func TestMetricsRecorders(t *testing.T) {
	m := New()
	m.RecordBudgetDecrement(context.Background(), "tokens")
	m.RecordBudgetExhaustion(context.Background(), "tokens")
	m.RecordBudgetCheckDuration(context.Background(), 0.001)
	m.RecordModeSelection(context.Background(), "DIRECT")
	m.RecordToTBranch(context.Background(), "COMPLETED")
	m.RecordCorrectionIteration(context.Background(), "CONVERGED")
	m.RecordCorrectionCost(context.Background(), 0.25)
	m.RecordCorrectionNonConvergence(context.Background(), "BUDGET_EXCEEDED")
	m.RecordTraceEvent(context.Background())
	m.RecordTraceDropped(context.Background())

	var nilMetrics *Metrics
	nilMetrics.RecordBudgetDecrement(context.Background(), "tokens")
	nilMetrics.RecordBudgetExhaustion(context.Background(), "tokens")
	nilMetrics.RecordBudgetCheckDuration(context.Background(), 0.001)
	nilMetrics.RecordModeSelection(context.Background(), "DIRECT")
	nilMetrics.RecordToTBranch(context.Background(), "COMPLETED")
	nilMetrics.RecordCorrectionIteration(context.Background(), "CONVERGED")
	nilMetrics.RecordCorrectionCost(context.Background(), 0.25)
	nilMetrics.RecordCorrectionNonConvergence(context.Background(), "BUDGET_EXCEEDED")
	nilMetrics.RecordTraceEvent(context.Background())
	nilMetrics.RecordTraceDropped(context.Background())
}
