package persistence

import (
	"context"
	"encoding/json"
	"errors"
	"io"
	"math"
	"net/http"
	"strings"
	"testing"

	"github.com/confluentinc/confluent-kafka-go/v2/kafka"
)

type roundTripper func(*http.Request) (*http.Response, error)

func (r roundTripper) RoundTrip(req *http.Request) (*http.Response, error) {
	return r(req)
}

type fakeKafkaProducer struct {
	event        kafka.Event
	err          error
	events       chan kafka.Event
	flushed      bool
	closed       bool
	skipDelivery bool
}

func (f *fakeKafkaProducer) Produce(_ *kafka.Message, delivery chan kafka.Event) error {
	if f.err != nil {
		return f.err
	}
	if !f.skipDelivery {
		delivery <- f.event
	}
	return nil
}

func (f *fakeKafkaProducer) Events() chan kafka.Event {
	if f.events == nil {
		f.events = make(chan kafka.Event)
	}
	return f.events
}

func (f *fakeKafkaProducer) Flush(int) int {
	f.flushed = true
	return 0
}

func (f *fakeKafkaProducer) Close() {
	f.closed = true
	if f.events != nil {
		close(f.events)
	}
}

func TestSplitCSVAndRedisClient(t *testing.T) {
	parts := splitCSV("a:1, b:2 ,, c:3")
	if len(parts) != 3 {
		t.Fatalf("splitCSV() len = %d, want 3", len(parts))
	}
	if NewRedisClient("") != nil {
		t.Fatal("expected nil redis client for empty address")
	}

	t.Setenv("REDIS_TEST_MODE", "standalone")
	t.Setenv("REDIS_PASSWORD", "cluster-secret")
	client := NewRedisClient("127.0.0.1:6379")
	if client == nil {
		t.Fatal("expected redis client for non-empty address")
	}
	if client.Options().ClusterSlots == nil {
		t.Fatal("expected standalone cluster slots override")
	}
	if client.Options().Password != "cluster-secret" {
		t.Fatalf("expected redis password to be propagated, got %q", client.Options().Password)
	}
	_ = client.Close()

	t.Setenv("REDIS_TEST_MODE", "")
	clusterClient := NewRedisClient("127.0.0.1:6379,127.0.0.1:6380")
	if clusterClient == nil {
		t.Fatal("expected redis cluster client")
	}
	if clusterClient.Options().ClusterSlots != nil {
		t.Fatal("expected cluster slots override to be disabled outside standalone mode")
	}
	_ = clusterClient.Close()
}

func TestPostgresAndKafkaHelpers(t *testing.T) {
	if NewPostgresPool("") != nil {
		t.Fatal("expected nil postgres pool for empty dsn")
	}

	pool := NewPostgresPool("postgres://user:pass@127.0.0.1:5432/musematic?sslmode=disable")
	if pool == nil {
		t.Fatal("expected postgres pool")
	}
	pool.Close()
	assertPanics(t, func() {
		_ = NewPostgresPool("://bad dsn")
	})

	var nilProducer *KafkaProducer
	if err := nilProducer.Produce(context.Background(), "topic", "key", []byte("value")); err != nil {
		t.Fatalf("nil producer Produce() error = %v", err)
	}
	nilProducer.Close()

	if NewKafkaProducer("") != nil {
		t.Fatal("expected nil kafka producer for empty brokers")
	}

	constructed := NewKafkaProducer("127.0.0.1:9092")
	if constructed == nil {
		t.Fatal("expected kafka producer for non-empty brokers")
	}
	constructed.Close()

	producer := &KafkaProducer{producer: &fakeKafkaProducer{event: &kafka.Message{}}}
	if err := producer.Produce(context.Background(), "topic", "key", []byte("value")); err != nil {
		t.Fatalf("Produce() error = %v", err)
	}

	failing := &KafkaProducer{producer: &fakeKafkaProducer{err: errors.New("produce failed")}}
	if err := failing.Produce(context.Background(), "topic", "key", []byte("value")); err == nil || err.Error() != "produce failed" {
		t.Fatalf("Produce() error = %v, want produce failed", err)
	}

	ctx, cancel := context.WithCancel(context.Background())
	cancel()
	blocked := &KafkaProducer{producer: &fakeKafkaProducer{events: make(chan kafka.Event), skipDelivery: true}}
	if err := blocked.Produce(ctx, "topic", "key", []byte("value")); !errors.Is(err, context.Canceled) {
		t.Fatalf("Produce() error = %v, want context canceled", err)
	}

	unexpected := &KafkaProducer{producer: &fakeKafkaProducer{event: kafka.Error{}}}
	if err := unexpected.Produce(context.Background(), "topic", "key", []byte("value")); err != nil {
		t.Fatalf("unexpected event should be ignored, got %v", err)
	}

	fake := &fakeKafkaProducer{event: &kafka.Message{}}
	closer := &KafkaProducer{producer: fake}
	closer.Close()
	if !fake.flushed || !fake.closed {
		t.Fatalf("expected flush and close, got flushed=%v closed=%v", fake.flushed, fake.closed)
	}
}

func TestMinIOClientUploadAndURL(t *testing.T) {
	client := NewMinIOClient("http://example.test", "bucket")
	if client == nil {
		t.Fatal("expected minio client")
	}
	client.client = &http.Client{
		Transport: roundTripper(func(r *http.Request) (*http.Response, error) {
			if r.Method != http.MethodPut {
				t.Fatalf("method = %s, want PUT", r.Method)
			}
			return &http.Response{
				StatusCode: http.StatusOK,
				Body:       io.NopCloser(strings.NewReader("ok")),
				Header:     make(http.Header),
			}, nil
		}),
	}
	if err := client.Upload(context.Background(), "path/object.txt", []byte("payload")); err != nil {
		t.Fatalf("Upload() error = %v", err)
	}
	if client.GetURL("path/object.txt") == "" {
		t.Fatal("expected object url")
	}
	if err := (*MinIOClient)(nil).Upload(context.Background(), "path/object.txt", []byte("payload")); err != nil {
		t.Fatalf("nil Upload() error = %v", err)
	}
	var nilClient *MinIOClient
	if nilClient.GetURL("path/object.txt") != "" {
		t.Fatal("expected empty url for nil minio client")
	}
	if NewMinIOClient("minio.internal:9000", "bucket").GetURL("path/object.txt") != "http://minio.internal:9000/bucket/path/object.txt" {
		t.Fatal("expected endpoint normalization")
	}
	if NewMinIOClient("", "bucket") != nil || NewMinIOClient("http://example.test", "") != nil {
		t.Fatal("expected nil minio client for missing endpoint or bucket")
	}
	if client.GetURL("/leading/slash.txt") != "http://example.test/bucket/leading/slash.txt" {
		t.Fatalf("unexpected escaped url: %s", client.GetURL("/leading/slash.txt"))
	}

	client.client = &http.Client{
		Transport: roundTripper(func(*http.Request) (*http.Response, error) {
			return &http.Response{
				StatusCode: http.StatusBadGateway,
				Status:     "502 Bad Gateway",
				Body:       io.NopCloser(strings.NewReader("bad gateway")),
				Header:     make(http.Header),
			}, nil
		}),
	}
	if err := client.Upload(context.Background(), "path/object.txt", []byte("payload")); err == nil {
		t.Fatal("expected upload error for bad response")
	}

	client.client = &http.Client{
		Transport: roundTripper(func(*http.Request) (*http.Response, error) {
			return nil, errors.New("dial failed")
		}),
	}
	if err := client.Upload(context.Background(), "path/object.txt", []byte("payload")); err == nil {
		t.Fatal("expected upload transport error")
	}
}

type uploadedTrace struct {
	path  string
	trace ConsolidatedTrace
}

func newRecordingTraceClient(t *testing.T) (*MinIOClient, *[]uploadedTrace) {
	t.Helper()

	client := NewMinIOClient("https://example.test", "bucket")
	if client == nil {
		t.Fatal("expected minio client")
	}

	uploads := []uploadedTrace{}
	client.client = &http.Client{
		Transport: roundTripper(func(r *http.Request) (*http.Response, error) {
			body, err := io.ReadAll(r.Body)
			if err != nil {
				return nil, err
			}
			trace := ConsolidatedTrace{}
			if err := json.Unmarshal(body, &trace); err != nil {
				return nil, err
			}
			uploads = append(uploads, uploadedTrace{path: r.URL.Path, trace: trace})
			return &http.Response{
				StatusCode: http.StatusOK,
				Body:       io.NopCloser(strings.NewReader("ok")),
				Header:     make(http.Header),
			}, nil
		}),
	}
	return client, &uploads
}

func assertUploadTraceResult(t *testing.T, upload uploadedTrace, wantPath string, wantTrace ConsolidatedTrace) {
	t.Helper()

	if upload.path != wantPath {
		t.Fatalf("uploaded path = %q, want %q", upload.path, wantPath)
	}
	if upload.trace.SchemaVersion != wantTrace.SchemaVersion || upload.trace.ExecutionID != wantTrace.ExecutionID || upload.trace.Technique != wantTrace.Technique {
		t.Fatalf("uploaded trace = %+v, want schema=%q execution=%q technique=%q", upload.trace, wantTrace.SchemaVersion, wantTrace.ExecutionID, wantTrace.Technique)
	}
}

func TestMinIOClientUploadTraceBuildsStorageKeys(t *testing.T) {
	client, uploads := newRecordingTraceClient(t)

	testCases := []struct {
		name      string
		execution string
		technique string
		session   string
		trace     ConsolidatedTrace
		wantKey   string
		wantPath  string
		wantTrace ConsolidatedTrace
	}{
		{
			name:      "debate defaults",
			execution: "exec-1",
			technique: "debate",
			session:   "session-1",
			trace:     ConsolidatedTrace{},
			wantKey:   "reasoning-debates/exec-1/session-1/trace.json",
			wantPath:  "/bucket/reasoning-debates/exec-1/session-1/trace.json",
			wantTrace: ConsolidatedTrace{SchemaVersion: "1.0", ExecutionID: "exec-1", Technique: "DEBATE"},
		},
		{
			name:      "self correction preserves explicit metadata",
			execution: "exec-2",
			technique: "self_correction",
			session:   "session-2",
			trace:     ConsolidatedTrace{SchemaVersion: "2.0", ExecutionID: "override-exec", Technique: "CUSTOM"},
			wantKey:   "reasoning-corrections/exec-2/session-2/trace.json",
			wantPath:  "/bucket/reasoning-corrections/exec-2/session-2/trace.json",
			wantTrace: ConsolidatedTrace{SchemaVersion: "2.0", ExecutionID: "override-exec", Technique: "CUSTOM"},
		},
		{
			name:      "react uses specialized filename",
			execution: "exec-3",
			technique: "react",
			session:   "session-3",
			trace:     ConsolidatedTrace{},
			wantKey:   "reasoning-traces/exec-3/session-3/react_trace.json",
			wantPath:  "/bucket/reasoning-traces/exec-3/session-3/react_trace.json",
			wantTrace: ConsolidatedTrace{SchemaVersion: "1.0", ExecutionID: "exec-3", Technique: "REACT"},
		},
		{
			name:      "default trace path",
			execution: "exec-4",
			technique: "chain_of_thought",
			session:   "session-4",
			trace:     ConsolidatedTrace{},
			wantKey:   "reasoning-traces/exec-4/session-4/trace.json",
			wantPath:  "/bucket/reasoning-traces/exec-4/session-4/trace.json",
			wantTrace: ConsolidatedTrace{SchemaVersion: "1.0", ExecutionID: "exec-4", Technique: "CHAIN_OF_THOUGHT"},
		},
	}

	for _, tc := range testCases {
		t.Run(tc.name, func(t *testing.T) {
			key, err := client.UploadTrace(context.Background(), tc.execution, tc.technique, tc.session, tc.trace)
			if err != nil {
				t.Fatalf("UploadTrace() error = %v", err)
			}
			if key != tc.wantKey {
				t.Fatalf("storage key = %q, want %q", key, tc.wantKey)
			}
			assertUploadTraceResult(t, (*uploads)[len(*uploads)-1], tc.wantPath, tc.wantTrace)
		})
	}
}

func TestMinIOClientUploadTracePropagatesErrors(t *testing.T) {
	client, _ := newRecordingTraceClient(t)
	client.client = &http.Client{
		Transport: roundTripper(func(*http.Request) (*http.Response, error) {
			return nil, errors.New("upload failed")
		}),
	}

	if _, err := client.UploadTrace(context.Background(), "exec-5", "debate", "session-5", ConsolidatedTrace{}); err == nil {
		t.Fatal("expected UploadTrace() transport error")
	}
	if _, err := client.UploadTrace(context.Background(), "exec-6", "debate", "session-6", ConsolidatedTrace{ComputeBudgetUsed: math.NaN()}); err == nil {
		t.Fatal("expected UploadTrace() marshal error")
	}
}

func assertPanics(t *testing.T, fn func()) {
	t.Helper()
	defer func() {
		if recover() == nil {
			t.Fatal("expected panic")
		}
	}()
	fn()
}
