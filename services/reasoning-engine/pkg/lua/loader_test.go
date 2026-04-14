package lua

import (
	"context"
	"errors"
	"strconv"
	"testing"

	"github.com/redis/go-redis/v9"
)

type fakeScripter struct {
	loaded []string
	errAt  int
}

func (f *fakeScripter) Eval(context.Context, string, []string, ...any) *redis.Cmd {
	return redis.NewCmd(context.Background())
}

func (f *fakeScripter) EvalRO(context.Context, string, []string, ...any) *redis.Cmd {
	return redis.NewCmd(context.Background())
}

func (f *fakeScripter) EvalSha(context.Context, string, []string, ...any) *redis.Cmd {
	return redis.NewCmd(context.Background())
}

func (f *fakeScripter) EvalShaRO(context.Context, string, []string, ...any) *redis.Cmd {
	return redis.NewCmd(context.Background())
}

func (f *fakeScripter) ScriptExists(context.Context, ...string) *redis.BoolSliceCmd {
	return redis.NewBoolSliceCmd(context.Background())
}

func (f *fakeScripter) ScriptLoad(_ context.Context, script string) *redis.StringCmd {
	f.loaded = append(f.loaded, script)
	if f.errAt == len(f.loaded) {
		return redis.NewStringResult("", errors.New("script load failed"))
	}
	return redis.NewStringResult("sha-"+strconv.Itoa(len(f.loaded)), nil)
}

func TestLoad(t *testing.T) {
	scripter := &fakeScripter{}
	loaded, err := Load(context.Background(), scripter)
	if err != nil {
		t.Fatalf("Load() error = %v", err)
	}
	if len(loaded) != 2 {
		t.Fatalf("loaded scripts = %d, want 2", len(loaded))
	}
}

func TestLoadReturnsScriptNameOnFailure(t *testing.T) {
	scripter := &fakeScripter{errAt: 2}
	loaded, err := Load(context.Background(), scripter)
	if err == nil {
		t.Fatal("expected Load() error")
	}
	if loaded != nil {
		t.Fatalf("loaded = %#v, want nil on error", loaded)
	}
	if len(scripter.loaded) != 2 {
		t.Fatalf("loaded scripts before failure = %d, want 2", len(scripter.loaded))
	}
}
