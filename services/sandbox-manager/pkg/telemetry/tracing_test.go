package telemetry

import (
	"context"
	"errors"
	"testing"

	"go.opentelemetry.io/otel/exporters/otlp/otlptrace/otlptracegrpc"
	sdkresource "go.opentelemetry.io/otel/sdk/resource"
	sdktrace "go.opentelemetry.io/otel/sdk/trace"
)

func TestSetupWithoutEndpointReturnsNoopShutdown(t *testing.T) {
	t.Parallel()

	shutdown, err := Setup(context.Background(), "sandbox-manager", "")
	if err != nil {
		t.Fatalf("Setup() error = %v", err)
	}
	if err := shutdown(context.Background()); err != nil {
		t.Fatalf("shutdown() error = %v", err)
	}
}

type fakeExporter struct{}

func (fakeExporter) ExportSpans(context.Context, []sdktrace.ReadOnlySpan) error { return nil }
func (fakeExporter) Shutdown(context.Context) error                             { return nil }

func TestSetupWithEndpointConfiguresExporter(t *testing.T) {
	originalExporter := newTraceExporter
	originalMerge := mergeTelemetryResource
	t.Cleanup(func() {
		newTraceExporter = originalExporter
		mergeTelemetryResource = originalMerge
	})

	var capturedOpts int
	newTraceExporter = func(_ context.Context, opts ...otlptracegrpc.Option) (sdktrace.SpanExporter, error) {
		capturedOpts = len(opts)
		return fakeExporter{}, nil
	}
	mergeTelemetryResource = sdkresource.Merge

	shutdown, err := Setup(context.Background(), "sandbox-manager", "http://otel-collector:4317")
	if err != nil {
		t.Fatalf("Setup() error = %v", err)
	}
	if capturedOpts != 2 {
		t.Fatalf("expected insecure endpoint to pass 2 options, got %d", capturedOpts)
	}
	if err := shutdown(context.Background()); err != nil {
		t.Fatalf("shutdown() error = %v", err)
	}
}

func TestSetupWithSecureEndpointOmitsInsecureOption(t *testing.T) {
	originalExporter := newTraceExporter
	originalMerge := mergeTelemetryResource
	t.Cleanup(func() {
		newTraceExporter = originalExporter
		mergeTelemetryResource = originalMerge
	})

	var capturedOpts int
	newTraceExporter = func(_ context.Context, opts ...otlptracegrpc.Option) (sdktrace.SpanExporter, error) {
		capturedOpts = len(opts)
		return fakeExporter{}, nil
	}
	mergeTelemetryResource = sdkresource.Merge

	if _, err := Setup(context.Background(), "sandbox-manager", "https://otel-collector:4317"); err != nil {
		t.Fatalf("Setup() error = %v", err)
	}
	if capturedOpts != 1 {
		t.Fatalf("expected secure endpoint to pass 1 option, got %d", capturedOpts)
	}
}

func TestSetupPropagatesExporterError(t *testing.T) {
	originalExporter := newTraceExporter
	t.Cleanup(func() { newTraceExporter = originalExporter })

	expectedErr := errors.New("exporter boom")
	newTraceExporter = func(context.Context, ...otlptracegrpc.Option) (sdktrace.SpanExporter, error) {
		return nil, expectedErr
	}

	if _, err := Setup(context.Background(), "sandbox-manager", "otel-collector:4317"); !errors.Is(err, expectedErr) {
		t.Fatalf("Setup() error = %v, want %v", err, expectedErr)
	}
}

func TestSetupPropagatesResourceMergeError(t *testing.T) {
	originalExporter := newTraceExporter
	originalMerge := mergeTelemetryResource
	t.Cleanup(func() {
		newTraceExporter = originalExporter
		mergeTelemetryResource = originalMerge
	})

	expectedErr := errors.New("merge boom")
	newTraceExporter = func(context.Context, ...otlptracegrpc.Option) (sdktrace.SpanExporter, error) {
		return fakeExporter{}, nil
	}
	mergeTelemetryResource = func(*sdkresource.Resource, *sdkresource.Resource) (*sdkresource.Resource, error) {
		return nil, expectedErr
	}

	if _, err := Setup(context.Background(), "sandbox-manager", "otel-collector:4317"); !errors.Is(err, expectedErr) {
		t.Fatalf("Setup() error = %v, want %v", err, expectedErr)
	}
}

func TestNormaliseEndpointStripsScheme(t *testing.T) {
	t.Parallel()

	if got := normaliseEndpoint("http://otel-collector:4317"); got != "otel-collector:4317" {
		t.Fatalf("normaliseEndpoint(http) = %q", got)
	}
	if got := normaliseEndpoint("https://otel-collector:4317"); got != "otel-collector:4317" {
		t.Fatalf("normaliseEndpoint(https) = %q", got)
	}
	if got := normaliseEndpoint("  https://otel-collector:4317  "); got != "otel-collector:4317" {
		t.Fatalf("normaliseEndpoint(trimmed) = %q", got)
	}
	if got := normaliseEndpoint("otel-collector:4317"); got != "otel-collector:4317" {
		t.Fatalf("normaliseEndpoint(raw) = %q", got)
	}
}
