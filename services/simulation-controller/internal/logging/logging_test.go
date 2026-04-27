package logging

import (
	"bytes"
	"context"
	"encoding/json"
	"log/slog"
	"testing"

	"google.golang.org/grpc/metadata"
)

func TestContextHandlerAddsStructuredFields(t *testing.T) {
	var buf bytes.Buffer
	logger := slog.New(NewContextHandler(slog.NewJSONHandler(&buf, nil), "simulation-controller", "platform-simulation"))
	ctx := WithFields(context.Background(), Fields{
		WorkspaceID:   "workspace-1",
		GoalID:        "goal-1",
		CorrelationID: "corr-1",
		TraceID:       "trace-1",
		UserID:        "user-1",
		ExecutionID:   "exec-1",
	})

	logger.InfoContext(ctx, "simulation started")

	var payload map[string]any
	if err := json.Unmarshal(buf.Bytes(), &payload); err != nil {
		t.Fatalf("decode log payload: %v", err)
	}
	if payload["service"] != "simulation-controller" || payload["bounded_context"] != "platform-simulation" {
		t.Fatalf("unexpected service metadata: %#v", payload)
	}
	if payload["workspace_id"] != "workspace-1" || payload["correlation_id"] != "corr-1" {
		t.Fatalf("missing context metadata: %#v", payload)
	}
}

func TestContextHandlerMissingContextDoesNotCrash(t *testing.T) {
	var buf bytes.Buffer
	logger := slog.New(NewContextHandler(slog.NewJSONHandler(&buf, nil), "simulation-controller", "platform-simulation"))

	logger.WarnContext(context.Background(), "simulation orphan")

	var payload map[string]any
	if err := json.Unmarshal(buf.Bytes(), &payload); err != nil {
		t.Fatalf("decode log payload: %v", err)
	}
	if _, ok := payload["workspace_id"]; ok {
		t.Fatalf("empty context value should not be emitted: %#v", payload)
	}
}

func TestWithGRPCMetadataExtractsCanonicalFields(t *testing.T) {
	var buf bytes.Buffer
	logger := slog.New(NewContextHandler(slog.NewJSONHandler(&buf, nil), "simulation-controller", "platform-simulation"))
	ctx := metadata.NewIncomingContext(context.Background(), metadata.Pairs(
		"workspace_id", "",
		"x-workspace-id", "workspace-1",
		"x-goal-id", "goal-1",
		"x-correlation-id", "corr-1",
		"x-trace-id", "trace-1",
		"x-user-id", "user-1",
		"x-execution-id", "exec-1",
	))

	logger.InfoContext(WithGRPCMetadata(ctx), "simulation grpc")

	var payload map[string]any
	if err := json.Unmarshal(buf.Bytes(), &payload); err != nil {
		t.Fatalf("decode log payload: %v", err)
	}
	for field, want := range map[string]string{
		"workspace_id":   "workspace-1",
		"goal_id":        "goal-1",
		"correlation_id": "corr-1",
		"trace_id":       "trace-1",
		"user_id":        "user-1",
		"execution_id":   "exec-1",
	} {
		if payload[field] != want {
			t.Fatalf("unexpected %s: %#v", field, payload)
		}
	}
}

func TestWithGRPCMetadataWithoutMetadataReturnsOriginalContext(t *testing.T) {
	ctx := context.Background()
	if got := WithGRPCMetadata(ctx); got != ctx {
		t.Fatalf("context without metadata should be returned unchanged")
	}
}

func TestContextHandlerAttrsGroupsAndConfigure(t *testing.T) {
	if logger := Configure("simulation-controller", "platform-simulation"); !logger.Enabled(context.Background(), slog.LevelInfo) {
		t.Fatalf("configured logger should be enabled for info")
	}

	var buf bytes.Buffer
	handler := NewContextHandler(slog.NewJSONHandler(&buf, nil), "simulation-controller", "platform-simulation").
		WithAttrs([]slog.Attr{slog.String("component", "grpc")}).
		WithGroup("request")

	slog.New(handler).InfoContext(context.Background(), "grouped", "method", "/simulation.Simulation/Create")

	var payload map[string]any
	if err := json.Unmarshal(buf.Bytes(), &payload); err != nil {
		t.Fatalf("decode log payload: %v", err)
	}
	if payload["component"] != "grpc" {
		t.Fatalf("handler attrs should be preserved: %#v", payload)
	}
	if _, ok := payload["request"].(map[string]any); !ok {
		t.Fatalf("handler group should wrap request attrs: %#v", payload)
	}
}
