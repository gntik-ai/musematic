package heartbeat

import (
	"context"
	"errors"
	"testing"
	"time"

	"github.com/redis/go-redis/v9"
)

type fakeRedisSetter struct {
	key   string
	value interface{}
	ttl   time.Duration
	err   error
}

func (f *fakeRedisSetter) Set(_ context.Context, key string, value interface{}, expiration time.Duration) *redis.StatusCmd {
	f.key = key
	f.value = value
	f.ttl = expiration
	return redis.NewStatusResult("OK", f.err)
}

type fakeHeartbeatStore struct {
	runtimeID string
	at        time.Time
	err       error
}

func (f *fakeHeartbeatStore) UpdateLastHeartbeat(_ context.Context, runtimeID string, at time.Time) error {
	f.runtimeID = runtimeID
	f.at = at
	return f.err
}

func TestReceiveHeartbeatWritesRedisAndStore(t *testing.T) {
	redisWriter := &fakeRedisSetter{}
	store := &fakeHeartbeatStore{}
	tracker := &HeartbeatTracker{Redis: redisWriter, Store: store, Timeout: time.Minute}

	if err := tracker.ReceiveHeartbeat(context.Background(), "exec-1"); err != nil {
		t.Fatalf("ReceiveHeartbeat returned error: %v", err)
	}
	if redisWriter.key != "heartbeat:exec-1" || redisWriter.ttl != time.Minute {
		t.Fatalf("unexpected redis write: %+v", redisWriter)
	}
	if store.runtimeID != "exec-1" || store.at.IsZero() {
		t.Fatalf("unexpected store update: %+v", store)
	}
}

func TestReceiveHeartbeatPropagatesRedisError(t *testing.T) {
	tracker := &HeartbeatTracker{
		Redis:   &fakeRedisSetter{err: errors.New("redis down")},
		Store:   &fakeHeartbeatStore{},
		Timeout: time.Minute,
	}

	if err := tracker.ReceiveHeartbeat(context.Background(), "exec-1"); err == nil {
		t.Fatalf("expected redis error")
	}
}

func TestHeartbeatKey(t *testing.T) {
	if got := heartbeatKey("runtime-1"); got != "heartbeat:runtime-1" {
		t.Fatalf("unexpected heartbeat key: %s", got)
	}
}

func TestReceiveHeartbeatPropagatesStoreError(t *testing.T) {
	store := &fakeHeartbeatStore{err: errors.New("store down")}
	tracker := &HeartbeatTracker{Redis: &fakeRedisSetter{}, Store: store, Timeout: time.Minute}

	if err := tracker.ReceiveHeartbeat(context.Background(), "exec-1"); err == nil {
		t.Fatalf("expected store error")
	}
}
