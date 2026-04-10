package lua

import (
	"context"
	"strconv"
	"testing"

	"github.com/redis/go-redis/v9"
)

type fakeScripter struct {
	loaded []string
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
