package health

import (
	"context"
	"encoding/json"
	"errors"
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/confluentinc/confluent-kafka-go/v2/kafka"
)

type fakePinger struct{ err error }

func (f fakePinger) Ping(context.Context) error { return f.err }

type fakeKafkaChecker struct{ err error }

func (f fakeKafkaChecker) GetMetadata(*string, bool, int) (*kafka.Metadata, error) {
	return &kafka.Metadata{}, f.err
}

type fakeK8sChecker struct{ err error }

func (f fakeK8sChecker) DoRaw(context.Context, string) ([]byte, error) { return []byte("ok"), f.err }

func TestLivezHandlerReturnsOK(t *testing.T) {
	req := httptest.NewRequest(http.MethodGet, "/healthz", nil)
	recorder := httptest.NewRecorder()

	LivezHandler(recorder, req)

	if recorder.Code != http.StatusOK {
		t.Fatalf("expected 200, got %d", recorder.Code)
	}
}

func TestReadyzHandlerReturnsAllChecksOK(t *testing.T) {
	req := httptest.NewRequest(http.MethodGet, "/readyz", nil)
	recorder := httptest.NewRecorder()

	ReadyzHandler(Dependencies{
		Postgres: fakePinger{},
		Redis:    fakePinger{},
		Kafka:    fakeKafkaChecker{},
		K8s:      fakeK8sChecker{},
	})(recorder, req)

	var body map[string]any
	if err := json.Unmarshal(recorder.Body.Bytes(), &body); err != nil {
		t.Fatalf("unmarshal failed: %v", err)
	}
	if recorder.Code != http.StatusOK || body["status"] != "ok" {
		t.Fatalf("unexpected ready response: %d %s", recorder.Code, recorder.Body.String())
	}
}

func TestReadyzHandlerReturnsServiceUnavailableWhenDependencyFails(t *testing.T) {
	req := httptest.NewRequest(http.MethodGet, "/readyz", nil)
	recorder := httptest.NewRecorder()

	ReadyzHandler(Dependencies{
		Postgres: fakePinger{err: errors.New("down")},
		Redis:    fakePinger{},
		Kafka:    fakeKafkaChecker{err: errors.New("broker unavailable")},
		K8s:      fakeK8sChecker{err: errors.New("api unavailable")},
	})(recorder, req)

	if recorder.Code != http.StatusServiceUnavailable {
		t.Fatalf("expected 503, got %d", recorder.Code)
	}
	var body struct {
		Status string            `json:"status"`
		Checks map[string]string `json:"checks"`
	}
	if err := json.Unmarshal(recorder.Body.Bytes(), &body); err != nil {
		t.Fatalf("unmarshal failed: %v", err)
	}
	if body.Status != "error" || body.Checks["postgres"] != "error" || body.Checks["redis"] != "ok" || body.Checks["kafka"] != "error" || body.Checks["k8s"] != "error" {
		t.Fatalf("unexpected body: %+v", body)
	}
}
