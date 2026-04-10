//go:build integration

package budget_tracker

import (
	"context"
	"os"
	"testing"

	"github.com/musematic/reasoning-engine/pkg/lua"
	"github.com/redis/go-redis/v9"
)

func TestRedisTrackerIntegration(t *testing.T) {
	addr := os.Getenv("REDIS_ADDR")
	if addr == "" {
		t.Skip("REDIS_ADDR is not set")
	}

	client := redis.NewClient(&redis.Options{Addr: addr})
	defer client.Close()

	scripts, err := lua.Load(context.Background(), client)
	if err != nil {
		t.Fatalf("Load() error = %v", err)
	}

	registry := NewEventRegistry()
	tracker := &RedisTracker{
		store:      redisStore{client: client},
		scripts:    scripts,
		registry:   registry,
		defaultTTL: 60,
	}

	if err := tracker.Allocate(context.Background(), "integration-exec", "step-1", BudgetAllocation{Tokens: 1000}, 60); err != nil {
		t.Fatalf("Allocate() error = %v", err)
	}

	for i := 0; i < 10; i++ {
		if _, err := tracker.Decrement(context.Background(), "integration-exec", "step-1", "tokens", 100); err != nil {
			t.Fatalf("Decrement() error = %v", err)
		}
	}

	status, err := tracker.GetStatus(context.Background(), "integration-exec", "step-1")
	if err != nil {
		t.Fatalf("GetStatus() error = %v", err)
	}
	if status.Used.Tokens != 1000 {
		t.Fatalf("used tokens = %d, want 1000", status.Used.Tokens)
	}
}
