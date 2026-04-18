package artifacts

import (
	"bytes"
	"context"
	"errors"
	"net/http"
	"net/http/httptest"
	"testing"
)

func TestS3UploaderUpload(t *testing.T) {
	t.Parallel()

	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodPut {
			t.Fatalf("unexpected method %s", r.Method)
		}
		if r.URL.Path != "/musematic-artifacts/sandbox-artifacts/exec-1/sandbox-1/result.txt" {
			t.Fatalf("unexpected path %s", r.URL.Path)
		}
		if got := r.Header.Get("Content-Type"); got != "text/plain" {
			t.Fatalf("unexpected content type %s", got)
		}
		payload := new(bytes.Buffer)
		if _, err := payload.ReadFrom(r.Body); err != nil {
			t.Fatalf("ReadFrom() error = %v", err)
		}
		if payload.String() != "ok" {
			t.Fatalf("unexpected payload %q", payload.String())
		}
		w.WriteHeader(http.StatusOK)
	}))
	defer server.Close()

	uploader := NewS3Uploader(server.URL, "musematic-artifacts")
	if err := uploader.Upload(context.Background(), "sandbox-artifacts/exec-1/sandbox-1/result.txt", bytes.NewBufferString("ok"), "text/plain"); err != nil {
		t.Fatalf("Upload() error = %v", err)
	}
}

func TestS3UploaderReturnsServerErrors(t *testing.T) {
	t.Parallel()

	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusInternalServerError)
	}))
	defer server.Close()

	uploader := NewS3Uploader(server.URL, "musematic-artifacts")
	if err := uploader.Upload(context.Background(), "sandbox-artifacts/result.txt", bytes.NewBufferString("ok"), "text/plain"); err == nil {
		t.Fatal("expected upload error")
	}
}

func TestNormaliseObjectStorageEndpointAddsScheme(t *testing.T) {
	t.Parallel()

	if got := normaliseObjectStorageEndpoint("minio:9000"); got != "http://minio:9000" {
		t.Fatalf("normaliseObjectStorageEndpoint() = %q", got)
	}
}

type roundTripFunc func(*http.Request) (*http.Response, error)

func (fn roundTripFunc) RoundTrip(request *http.Request) (*http.Response, error) {
	return fn(request)
}

func TestS3UploaderHelpersAndErrors(t *testing.T) {
	t.Parallel()

	if NewS3Uploader("", "bucket") != nil {
		t.Fatal("expected empty endpoint to return nil uploader")
	}
	if NewS3Uploader("http://minio:9000", "") != nil {
		t.Fatal("expected empty bucket to return nil uploader")
	}
	if err := (*S3Uploader)(nil).Upload(context.Background(), "key", bytes.NewBufferString("ok"), "text/plain"); err != nil {
		t.Fatalf("nil Upload() error = %v", err)
	}

	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if got := r.Header.Get("Content-Type"); got != "application/octet-stream" {
			t.Fatalf("unexpected default content type %s", got)
		}
		w.WriteHeader(http.StatusOK)
	}))
	defer server.Close()

	uploader := NewS3Uploader(server.URL, "musematic-artifacts")
	if err := uploader.Upload(context.Background(), "sandbox-artifacts/result.txt", bytes.NewBufferString("ok"), ""); err != nil {
		t.Fatalf("Upload() default content type error = %v", err)
	}

	expectedErr := errors.New("transport boom")
	uploader = &S3Uploader{
		bucket:   "musematic-artifacts",
		endpoint: server.URL,
		client: &http.Client{
			Transport: roundTripFunc(func(*http.Request) (*http.Response, error) {
				return nil, expectedErr
			}),
		},
	}
	if err := uploader.Upload(context.Background(), "sandbox-artifacts/result.txt", bytes.NewBufferString("ok"), "text/plain"); !errors.Is(err, expectedErr) {
		t.Fatalf("Upload() error = %v, want %v", err, expectedErr)
	}
}
