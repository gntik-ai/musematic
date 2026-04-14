package health

import (
	"context"
	"errors"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
)

type healthPostgresStub struct{ err error }

func (s healthPostgresStub) Ping(context.Context) error { return s.err }

type healthKafkaStub struct{ err error }

func (s healthKafkaStub) GetMetadata(*string, bool, int) (*struct{}, error) {
	return &struct{}{}, s.err
}

type healthK8sStub struct{ err error }

func (s healthK8sStub) DoRaw(context.Context, string) ([]byte, error) { return []byte("ok"), s.err }

func TestLivezHandler(t *testing.T) {
	t.Parallel()

	recorder := httptest.NewRecorder()
	request := httptest.NewRequest(http.MethodGet, "/healthz", nil)
	LivezHandler(recorder, request)

	if recorder.Code != http.StatusOK {
		t.Fatalf("LivezHandler() status = %d", recorder.Code)
	}
	if got := recorder.Header().Get("Content-Type"); got != "application/json" {
		t.Fatalf("LivezHandler() content-type = %q", got)
	}
	if body := recorder.Body.String(); !strings.Contains(body, `"status":"ok"`) {
		t.Fatalf("LivezHandler() body = %q", body)
	}
}

func TestReadyzHandlerSuccess(t *testing.T) {
	t.Parallel()

	recorder := httptest.NewRecorder()
	request := httptest.NewRequest(http.MethodGet, "/readyz", nil)
	ReadyzHandler(Dependencies{
		Postgres: healthPostgresStub{},
		Kafka:    healthKafkaStub{},
		K8s:      healthK8sStub{},
	}).ServeHTTP(recorder, request)

	if recorder.Code != http.StatusOK {
		t.Fatalf("ReadyzHandler() status = %d", recorder.Code)
	}
	if body := recorder.Body.String(); !strings.Contains(body, `"status":"ok"`) {
		t.Fatalf("ReadyzHandler() body = %q", body)
	}
}

func TestReadyzHandlerDependencyFailure(t *testing.T) {
	t.Parallel()

	cases := []Dependencies{
		{Postgres: healthPostgresStub{err: errors.New("postgres down")}},
		{Kafka: healthKafkaStub{err: errors.New("kafka down")}},
		{K8s: healthK8sStub{err: errors.New("k8s down")}},
	}

	for _, deps := range cases {
		recorder := httptest.NewRecorder()
		request := httptest.NewRequest(http.MethodGet, "/readyz", nil)
		ReadyzHandler(deps).ServeHTTP(recorder, request)
		if recorder.Code != http.StatusServiceUnavailable {
			t.Fatalf("ReadyzHandler() status = %d", recorder.Code)
		}
	}
}
