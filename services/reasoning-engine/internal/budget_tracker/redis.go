package budget_tracker

import (
	"context"
	"fmt"
	"strconv"
	"time"

	"github.com/musematic/reasoning-engine/pkg/metrics"
	"github.com/redis/go-redis/v9"
)

type commandStore interface {
	Exists(ctx context.Context, key string) (int64, error)
	HSet(ctx context.Context, key string, values map[string]any) error
	HSetFields(ctx context.Context, key string, values ...any) error
	Expire(ctx context.Context, key string, ttl time.Duration) error
	EvalSha(ctx context.Context, sha string, keys []string, args ...any) (any, error)
	HGetAll(ctx context.Context, key string) (map[string]string, error)
}

type redisStore struct {
	client redis.Cmdable
}

func (r redisStore) Exists(ctx context.Context, key string) (int64, error) {
	return r.client.Exists(ctx, key).Result()
}

func (r redisStore) HSet(ctx context.Context, key string, values map[string]any) error {
	return r.client.HSet(ctx, key, values).Err()
}

func (r redisStore) HSetFields(ctx context.Context, key string, values ...any) error {
	return r.client.HSet(ctx, key, values...).Err()
}

func (r redisStore) Expire(ctx context.Context, key string, ttl time.Duration) error {
	return r.client.Expire(ctx, key, ttl).Err()
}

func (r redisStore) EvalSha(ctx context.Context, sha string, keys []string, args ...any) (any, error) {
	return r.client.EvalSha(ctx, sha, keys, args...).Result()
}

func (r redisStore) HGetAll(ctx context.Context, key string) (map[string]string, error) {
	return r.client.HGetAll(ctx, key).Result()
}

type RedisTracker struct {
	store      commandStore
	scripts    map[string]string
	registry   *EventRegistry
	metrics    *metrics.Metrics
	defaultTTL int64
	now        func() time.Time
}

func NewRedisTracker(client redis.Cmdable, scripts map[string]string, registry *EventRegistry, telemetry *metrics.Metrics, defaultTTL int64) *RedisTracker {
	if defaultTTL <= 0 {
		defaultTTL = 3600
	}
	var store commandStore
	if client != nil {
		store = redisStore{client: client}
	}
	return &RedisTracker{
		store:      store,
		scripts:    scripts,
		registry:   registry,
		metrics:    telemetry,
		defaultTTL: defaultTTL,
		now:        func() time.Time { return time.Now().UTC() },
	}
}

func (t *RedisTracker) Allocate(ctx context.Context, execID, stepID string, limits BudgetAllocation, ttlSecs int64) error {
	if t.store == nil {
		return fmt.Errorf("redis client is required")
	}
	if limits.Tokens <= 0 && limits.Rounds <= 0 && limits.Cost <= 0 && limits.TimeMS <= 0 {
		return fmt.Errorf("at least one positive budget limit is required")
	}

	key := redisKey(execID, stepID)
	exists, err := t.store.Exists(ctx, key)
	if err != nil {
		return err
	}
	if exists > 0 {
		return ErrAlreadyExists
	}

	now := t.now()
	values := map[string]any{
		"execution_id":    execID,
		"step_id":         stepID,
		"used_tokens":     0,
		"max_tokens":      limits.Tokens,
		"used_rounds":     0,
		"max_rounds":      limits.Rounds,
		"used_cost":       0,
		"max_cost":        limits.Cost,
		"start_time_ms":   now.UnixMilli(),
		"allocated_at_ms": now.UnixMilli(),
		"max_time_ms":     limits.TimeMS,
		"status":          "ALLOCATED",
	}
	if err := t.store.HSet(ctx, key, values); err != nil {
		return err
	}

	if ttlSecs <= 0 {
		ttlSecs = t.defaultTTL
	}
	if err := t.store.Expire(ctx, key, time.Duration(ttlSecs)*time.Second); err != nil {
		return err
	}

	if t.registry != nil {
		t.registry.Register(Key(execID, stepID))
		t.registry.Publish(Key(execID, stepID), BudgetEvent{
			ExecutionID:  execID,
			StepID:       stepID,
			EventType:    "ALLOCATED",
			Dimension:    "tokens",
			CurrentValue: 0,
			MaxValue:     float64(limits.Tokens),
			OccurredAt:   now,
		})
	}
	return nil
}

func (t *RedisTracker) Decrement(ctx context.Context, execID, stepID, dimension string, amount float64) (float64, error) {
	if t.store == nil {
		return 0, fmt.Errorf("redis client is required")
	}
	if amount <= 0 {
		return 0, fmt.Errorf("amount must be positive")
	}

	start := time.Now()
	key := redisKey(execID, stepID)
	status, err := t.GetStatus(ctx, execID, stepID)
	if err != nil {
		return 0, err
	}
	if exhaustedByTime(status) {
		if err := t.store.HSetFields(ctx, key, "status", "EXHAUSTED"); err == nil && t.registry != nil {
			t.registry.PublishExceeded(Key(execID, stepID), status, "time")
		}
		return 0, ErrBudgetExceeded
	}

	field := fieldForDimension(dimension)
	if field == "" {
		return 0, fmt.Errorf("unsupported dimension %q", dimension)
	}

	sha := t.scripts["budget_decrement"]
	result, err := t.store.EvalSha(ctx, sha, []string{key}, field, amount)
	duration := time.Since(start).Seconds()
	t.metrics.RecordBudgetCheckDuration(ctx, duration)
	if err != nil {
		return 0, err
	}

	current, err := parseFloat(result)
	if err != nil {
		return 0, err
	}
	if current < 0 {
		if err := t.store.HSetFields(ctx, key, "status", "EXHAUSTED"); err != nil {
			return 0, err
		}
		status.Status = "EXHAUSTED"
		if t.registry != nil {
			t.registry.PublishExceeded(Key(execID, stepID), status, dimension)
		}
		return 0, ErrBudgetExceeded
	}

	if err := t.store.HSetFields(ctx, key, "status", "ACTIVE"); err != nil {
		return 0, err
	}
	t.metrics.RecordBudgetDecrement(ctx, dimension)

	updated, err := t.GetStatus(ctx, execID, stepID)
	if err == nil && t.registry != nil {
		t.registry.EvaluateAndPublish(Key(execID, stepID), updated)
	}
	return current, nil
}

func (t *RedisTracker) GetStatus(ctx context.Context, execID, stepID string) (*BudgetStatus, error) {
	if t.store == nil {
		return nil, fmt.Errorf("redis client is required")
	}

	values, err := t.store.HGetAll(ctx, redisKey(execID, stepID))
	if err != nil {
		return nil, err
	}
	if len(values) == 0 {
		return nil, ErrBudgetNotFound
	}

	startTime := parseInt64(values["start_time_ms"])
	allocatedAt := parseInt64(values["allocated_at_ms"])
	elapsed := t.now().UnixMilli() - startTime
	if elapsed < 0 {
		elapsed = 0
	}

	status := &BudgetStatus{
		ExecutionID: values["execution_id"],
		StepID:      values["step_id"],
		Limits: BudgetAllocation{
			Tokens: parseInt64(values["max_tokens"]),
			Rounds: parseInt64(values["max_rounds"]),
			Cost:   parseFloat64(values["max_cost"]),
			TimeMS: parseInt64(values["max_time_ms"]),
		},
		Used: BudgetAllocation{
			Tokens: parseInt64(values["used_tokens"]),
			Rounds: parseInt64(values["used_rounds"]),
			Cost:   parseFloat64(values["used_cost"]),
			TimeMS: elapsed,
		},
		Status:      values["status"],
		AllocatedAt: time.UnixMilli(allocatedAt).UTC(),
	}

	return status, nil
}

func exhaustedByTime(status *BudgetStatus) bool {
	if status == nil || status.Limits.TimeMS <= 0 {
		return false
	}
	return status.Used.TimeMS >= status.Limits.TimeMS
}

func redisKey(execID, stepID string) string {
	return "budget:" + execID + ":" + stepID
}

func fieldForDimension(dimension string) string {
	switch dimension {
	case "tokens":
		return "used_tokens"
	case "rounds":
		return "used_rounds"
	case "cost":
		return "used_cost"
	default:
		return ""
	}
}

func parseFloat(value any) (float64, error) {
	switch typed := value.(type) {
	case int64:
		return float64(typed), nil
	case float64:
		return typed, nil
	case string:
		return strconv.ParseFloat(typed, 64)
	default:
		return 0, fmt.Errorf("unexpected numeric type %T", value)
	}
}

func parseInt64(value string) int64 {
	if value == "" {
		return 0
	}
	parsed, err := strconv.ParseInt(value, 10, 64)
	if err == nil {
		return parsed
	}
	floatValue, err := strconv.ParseFloat(value, 64)
	if err != nil {
		return 0
	}
	return int64(floatValue)
}

func parseFloat64(value string) float64 {
	if value == "" {
		return 0
	}
	parsed, err := strconv.ParseFloat(value, 64)
	if err != nil {
		return 0
	}
	return parsed
}
