package logging

import (
	"bytes"
	"context"
	"encoding/json"
	"log/slog"
	"testing"
)

func TestContextHandlerAddsStructuredFields(t *testing.T) {
	var buf bytes.Buffer
	logger := slog.New(NewContextHandler(slog.NewJSONHandler(&buf, nil), "sandbox-manager", "platform-execution"))
	ctx := WithFields(context.Background(), Fields{
		WorkspaceID:   "workspace-1",
		GoalID:        "goal-1",
		CorrelationID: "corr-1",
		TraceID:       "trace-1",
		UserID:        "user-1",
		ExecutionID:   "exec-1",
	})

	logger.InfoContext(ctx, "sandbox created")

	var payload map[string]any
	if err := json.Unmarshal(buf.Bytes(), &payload); err != nil {
		t.Fatalf("decode log payload: %v", err)
	}
	if payload["service"] != "sandbox-manager" || payload["bounded_context"] != "platform-execution" {
		t.Fatalf("unexpected service metadata: %#v", payload)
	}
	if payload["workspace_id"] != "workspace-1" || payload["correlation_id"] != "corr-1" {
		t.Fatalf("missing context metadata: %#v", payload)
	}
}

func TestContextHandlerMissingContextDoesNotCrash(t *testing.T) {
	var buf bytes.Buffer
	logger := slog.New(NewContextHandler(slog.NewJSONHandler(&buf, nil), "sandbox-manager", "platform-execution"))

	logger.WarnContext(context.Background(), "sandbox idle")

	var payload map[string]any
	if err := json.Unmarshal(buf.Bytes(), &payload); err != nil {
		t.Fatalf("decode log payload: %v", err)
	}
	if _, ok := payload["workspace_id"]; ok {
		t.Fatalf("empty context value should not be emitted: %#v", payload)
	}
}
