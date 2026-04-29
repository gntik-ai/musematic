package logging

import (
	"context"
	"io"
	"log/slog"
	"os"
	"strings"

	"google.golang.org/grpc/metadata"
)

type ctxKey string

const (
	workspaceIDKey   ctxKey = "workspace_id"
	goalIDKey        ctxKey = "goal_id"
	correlationIDKey ctxKey = "correlation_id"
	traceIDKey       ctxKey = "trace_id"
	userIDKey        ctxKey = "user_id"
	executionIDKey   ctxKey = "execution_id"
)

type Fields struct {
	WorkspaceID   string
	GoalID        string
	CorrelationID string
	TraceID       string
	UserID        string
	ExecutionID   string
}

type ContextHandler struct {
	handler        slog.Handler
	service        string
	boundedContext string
}

func Configure(service string, boundedContext string) *slog.Logger {
	return slog.New(NewContextHandler(NewJSONHandler(os.Stdout), service, boundedContext))
}

func NewJSONHandler(w io.Writer) *slog.JSONHandler {
	return slog.NewJSONHandler(w, &slog.HandlerOptions{ReplaceAttr: replaceContractAttrs})
}

func NewContextHandler(handler slog.Handler, service string, boundedContext string) *ContextHandler {
	return &ContextHandler{handler: handler, service: service, boundedContext: boundedContext}
}

func WithFields(ctx context.Context, fields Fields) context.Context {
	values := map[ctxKey]string{
		workspaceIDKey:   fields.WorkspaceID,
		goalIDKey:        fields.GoalID,
		correlationIDKey: fields.CorrelationID,
		traceIDKey:       fields.TraceID,
		userIDKey:        fields.UserID,
		executionIDKey:   fields.ExecutionID,
	}
	for key, value := range values {
		if value != "" {
			ctx = context.WithValue(ctx, key, value)
		}
	}
	return ctx
}

func WithGRPCMetadata(ctx context.Context) context.Context {
	md, ok := metadata.FromIncomingContext(ctx)
	if !ok {
		return ctx
	}
	return WithFields(ctx, Fields{
		WorkspaceID:   firstMetadata(md, "workspace_id", "x-workspace-id"),
		GoalID:        firstMetadata(md, "goal_id", "x-goal-id"),
		CorrelationID: firstMetadata(md, "correlation_id", "x-correlation-id"),
		TraceID:       firstMetadata(md, "trace_id", "x-trace-id"),
		UserID:        firstMetadata(md, "user_id", "x-user-id"),
		ExecutionID:   firstMetadata(md, "execution_id", "x-execution-id"),
	})
}

func (h *ContextHandler) Enabled(ctx context.Context, level slog.Level) bool {
	return h.handler.Enabled(ctx, level)
}

func (h *ContextHandler) Handle(ctx context.Context, record slog.Record) error {
	record.AddAttrs(
		slog.String("service", h.service),
		slog.String("bounded_context", h.boundedContext),
	)
	for key, attrName := range map[ctxKey]string{
		workspaceIDKey:   "workspace_id",
		goalIDKey:        "goal_id",
		correlationIDKey: "correlation_id",
		traceIDKey:       "trace_id",
		userIDKey:        "user_id",
		executionIDKey:   "execution_id",
	} {
		if value, ok := ctx.Value(key).(string); ok && value != "" {
			record.AddAttrs(slog.String(attrName, value))
		}
	}
	return h.handler.Handle(ctx, record)
}

func (h *ContextHandler) WithAttrs(attrs []slog.Attr) slog.Handler {
	return &ContextHandler{
		handler:        h.handler.WithAttrs(attrs),
		service:        h.service,
		boundedContext: h.boundedContext,
	}
}

func (h *ContextHandler) WithGroup(name string) slog.Handler {
	return &ContextHandler{
		handler:        h.handler.WithGroup(name),
		service:        h.service,
		boundedContext: h.boundedContext,
	}
}

func firstMetadata(md metadata.MD, keys ...string) string {
	for _, key := range keys {
		values := md.Get(key)
		if len(values) > 0 && values[0] != "" {
			return values[0]
		}
	}
	return ""
}

func replaceContractAttrs(_ []string, attr slog.Attr) slog.Attr {
	switch attr.Key {
	case slog.TimeKey:
		attr.Key = "timestamp"
	case slog.MessageKey:
		attr.Key = "message"
	case slog.LevelKey:
		attr.Key = "level"
		attr.Value = slog.StringValue(strings.ToLower(attr.Value.String()))
	}
	return attr
}
