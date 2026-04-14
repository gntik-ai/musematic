package budget_tracker

import (
	"context"
	"errors"
	"testing"
	"time"

	"github.com/redis/go-redis/v9"
)

type fakeRedisHashClient struct {
	existsResult  int64
	existsErr     error
	hsetErr       error
	expireErr     error
	evalResult    any
	evalErr       error
	hgetallResult map[string]string
	hgetallErr    error
}

func (c *fakeRedisHashClient) Exists(_ context.Context, _ ...string) *redis.IntCmd {
	return redis.NewIntResult(c.existsResult, c.existsErr)
}

func (c *fakeRedisHashClient) HSet(_ context.Context, _ string, _ ...any) *redis.IntCmd {
	return redis.NewIntResult(1, c.hsetErr)
}

func (c *fakeRedisHashClient) Expire(_ context.Context, _ string, _ time.Duration) *redis.BoolCmd {
	return redis.NewBoolResult(true, c.expireErr)
}

func (c *fakeRedisHashClient) EvalSha(_ context.Context, _ string, _ []string, _ ...any) *redis.Cmd {
	return redis.NewCmdResult(c.evalResult, c.evalErr)
}

func (c *fakeRedisHashClient) HGetAll(_ context.Context, _ string) *redis.MapStringStringCmd {
	return redis.NewMapStringStringResult(c.hgetallResult, c.hgetallErr)
}

func TestRedisStoreWrapsRedisClientCommands(t *testing.T) {
	t.Parallel()

	store := redisStore{client: &fakeRedisHashClient{
		existsResult:  1,
		evalResult:    "4.5",
		hgetallResult: map[string]string{"status": "ACTIVE"},
	}}

	if exists, err := store.Exists(context.Background(), "budget:key"); err != nil || exists != 1 {
		t.Fatalf("Exists() = %d, %v", exists, err)
	}
	if err := store.HSet(context.Background(), "budget:key", map[string]any{"status": "ACTIVE"}); err != nil {
		t.Fatalf("HSet() error = %v", err)
	}
	if err := store.HSetFields(context.Background(), "budget:key", "status", "EXHAUSTED"); err != nil {
		t.Fatalf("HSetFields() error = %v", err)
	}
	if err := store.Expire(context.Background(), "budget:key", time.Minute); err != nil {
		t.Fatalf("Expire() error = %v", err)
	}
	if value, err := store.EvalSha(context.Background(), "sha", []string{"budget:key"}, "used_tokens", 4.5); err != nil || value != "4.5" {
		t.Fatalf("EvalSha() = %#v, %v", value, err)
	}
	if values, err := store.HGetAll(context.Background(), "budget:key"); err != nil || values["status"] != "ACTIVE" {
		t.Fatalf("HGetAll() = %#v, %v", values, err)
	}
}

func TestRedisStorePropagatesErrors(t *testing.T) {
	t.Parallel()

	expected := errors.New("redis failed")
	store := redisStore{client: &fakeRedisHashClient{
		existsErr:  expected,
		hsetErr:    expected,
		expireErr:  expected,
		evalErr:    expected,
		hgetallErr: expected,
	}}

	if _, err := store.Exists(context.Background(), "budget:key"); !errors.Is(err, expected) {
		t.Fatalf("Exists() error = %v", err)
	}
	if err := store.HSet(context.Background(), "budget:key", map[string]any{"status": "ACTIVE"}); !errors.Is(err, expected) {
		t.Fatalf("HSet() error = %v", err)
	}
	if err := store.HSetFields(context.Background(), "budget:key", "status", "ACTIVE"); !errors.Is(err, expected) {
		t.Fatalf("HSetFields() error = %v", err)
	}
	if err := store.Expire(context.Background(), "budget:key", time.Minute); !errors.Is(err, expected) {
		t.Fatalf("Expire() error = %v", err)
	}
	if _, err := store.EvalSha(context.Background(), "sha", []string{"budget:key"}, "used_tokens", 1); !errors.Is(err, expected) {
		t.Fatalf("EvalSha() error = %v", err)
	}
	if _, err := store.HGetAll(context.Background(), "budget:key"); !errors.Is(err, expected) {
		t.Fatalf("HGetAll() error = %v", err)
	}
}
