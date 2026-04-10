package ate_runner

import (
	"context"
	"encoding/json"
	"strconv"
	"strings"
	"time"

	simulationv1 "github.com/musematic/simulation-controller/api/grpc/v1"
	"github.com/musematic/simulation-controller/internal/event_streamer"
	"github.com/musematic/simulation-controller/pkg/metrics"
	"github.com/musematic/simulation-controller/pkg/persistence"
)

type AggregationRequest struct {
	SimulationID      string
	SessionID         string
	AgentID           string
	ExpectedScenarios []*simulationv1.ATEScenario
}

type ResultsAggregator struct {
	Fanout   *event_streamer.FanoutRegistry
	Store    resultsStore
	Uploader interface {
		Upload(ctx context.Context, key string, data []byte, metadata map[string]string) error
	}
	Metrics *metrics.Metrics
}

type resultsStore interface {
	InsertATEResult(ctx context.Context, record persistence.ATEResultRecord) error
	UpdateATEReport(ctx context.Context, sessionID, objectKey string, completedAt time.Time) error
}

type scenarioReport struct {
	ScenarioID      string   `json:"scenario_id"`
	Passed          bool     `json:"passed"`
	QualityScore    *float64 `json:"quality_score,omitempty"`
	LatencyMS       *int32   `json:"latency_ms,omitempty"`
	Cost            *float64 `json:"cost,omitempty"`
	SafetyCompliant *bool    `json:"safety_compliant,omitempty"`
	Error           string   `json:"error,omitempty"`
}

type ateReport struct {
	SessionID string           `json:"session_id"`
	AgentID   string           `json:"agent_id"`
	Scenarios []scenarioReport `json:"scenarios"`
	Summary   struct {
		Total  int `json:"total"`
		Passed int `json:"passed"`
		Failed int `json:"failed"`
	} `json:"summary"`
}

func (a *ResultsAggregator) Run(ctx context.Context, req AggregationRequest) error {
	if a == nil || a.Fanout == nil {
		return nil
	}

	ch := a.Fanout.Subscribe(req.SimulationID)
	defer a.Fanout.Unsubscribe(req.SimulationID, ch)

	seen := map[string]scenarioReport{}
	for {
		select {
		case <-ctx.Done():
			return ctx.Err()
		case event, ok := <-ch:
			if !ok {
				return nil
			}
			if event.GetEventType() != "ATE_SCENARIO_COMPLETED" {
				continue
			}
			result := reportFromEvent(event)
			seen[result.ScenarioID] = result

			if a.Store != nil {
				record := persistence.ATEResultRecord{
					SessionID:       req.SessionID,
					ScenarioID:      result.ScenarioID,
					Passed:          result.Passed,
					QualityScore:    result.QualityScore,
					LatencyMS:       result.LatencyMS,
					Cost:            result.Cost,
					SafetyCompliant: result.SafetyCompliant,
					ErrorMessage:    result.Error,
				}
				if err := a.Store.InsertATEResult(ctx, record); err != nil {
					return err
				}
			}
			if a.Metrics != nil {
				outcome := "failed"
				if result.Passed {
					outcome = "passed"
				}
				a.Metrics.RecordATEScenario(ctx, outcome)
			}

			if len(seen) < len(req.ExpectedScenarios) {
				continue
			}

			report := buildReport(req, seen)
			payload, err := json.Marshal(report)
			if err != nil {
				return err
			}
			objectKey := req.SimulationID + "/ate-report.json"
			if a.Uploader != nil {
				if err := a.Uploader.Upload(ctx, objectKey, payload, map[string]string{
					"x-amz-meta-simulation":    "true",
					"x-amz-meta-simulation-id": req.SimulationID,
				}); err != nil {
					return err
				}
			}
			if a.Store != nil {
				if err := a.Store.UpdateATEReport(ctx, req.SessionID, objectKey, time.Now().UTC()); err != nil {
					return err
				}
			}
			return nil
		}
	}
}

func reportFromEvent(event *simulationv1.SimulationEvent) scenarioReport {
	metadata := event.GetMetadata()
	report := scenarioReport{
		ScenarioID: metadata["scenario_id"],
		Passed:     parseBool(metadata["passed"]),
		Error:      metadata["error"],
	}
	report.QualityScore = parseFloat(metadata["quality_score"])
	report.Cost = parseFloat(metadata["cost"])
	report.LatencyMS = parseInt32(metadata["latency_ms"])
	report.SafetyCompliant = parseBoolPtr(metadata["safety_compliant"])
	return report
}

func buildReport(req AggregationRequest, results map[string]scenarioReport) ateReport {
	report := ateReport{
		SessionID: req.SessionID,
		AgentID:   req.AgentID,
		Scenarios: make([]scenarioReport, 0, len(results)),
	}
	for _, scenario := range req.ExpectedScenarios {
		result, ok := results[scenario.GetScenarioId()]
		if !ok {
			continue
		}
		report.Scenarios = append(report.Scenarios, result)
		report.Summary.Total++
		if result.Passed {
			report.Summary.Passed++
		} else {
			report.Summary.Failed++
		}
	}
	return report
}

func parseBool(value string) bool {
	return strings.EqualFold(value, "true")
}

func parseBoolPtr(value string) *bool {
	if value == "" {
		return nil
	}
	parsed := parseBool(value)
	return &parsed
}

func parseFloat(value string) *float64 {
	if value == "" {
		return nil
	}
	parsed, err := strconv.ParseFloat(value, 64)
	if err != nil {
		return nil
	}
	return &parsed
}

func parseInt32(value string) *int32 {
	if value == "" {
		return nil
	}
	parsed, err := strconv.ParseInt(value, 10, 32)
	if err != nil {
		return nil
	}
	cast := int32(parsed)
	return &cast
}
