package telemetry

import (
	"context"
	"errors"
	"testing"

	sdkmetric "go.opentelemetry.io/otel/sdk/metric"
	sdkresource "go.opentelemetry.io/otel/sdk/resource"
	sdktrace "go.opentelemetry.io/otel/sdk/trace"
)

type fakeSpanExporter struct{}

func (fakeSpanExporter) ExportSpans(context.Context, []sdktrace.ReadOnlySpan) error { return nil }
func (fakeSpanExporter) Shutdown(context.Context) error                             { return nil }

func TestSetupWithoutEndpointReturnsNoopShutdown(t *testing.T) {
	t.Parallel()

	shutdown, err := Setup(context.Background(), "reasoning-engine", "")
	if err != nil {
		t.Fatalf("Setup() error = %v", err)
	}
	if err := shutdown(context.Background()); err != nil {
		t.Fatalf("shutdown() error = %v", err)
	}
}

func TestSetupWithEndpointConfiguresTelemetry(t *testing.T) {
	originalTrace := newTraceExporter
	originalMetric := newMetricReader
	originalMerge := mergeTelemetryResource
	t.Cleanup(func() {
		newTraceExporter = originalTrace
		newMetricReader = originalMetric
		mergeTelemetryResource = originalMerge
	})

	var traceEndpoint string
	var metricEndpoint string
	var traceInsecure bool
	var metricInsecure bool

	newTraceExporter = func(_ context.Context, endpoint string, insecure bool) (sdktrace.SpanExporter, error) {
		traceEndpoint = endpoint
		traceInsecure = insecure
		return fakeSpanExporter{}, nil
	}
	newMetricReader = func(_ context.Context, endpoint string, insecure bool) (sdkmetric.Reader, error) {
		metricEndpoint = endpoint
		metricInsecure = insecure
		return sdkmetric.NewManualReader(), nil
	}
	mergeTelemetryResource = sdkresource.Merge

	shutdown, err := Setup(context.Background(), "reasoning-engine", "http://otel-collector:4317")
	if err != nil {
		t.Fatalf("Setup() error = %v", err)
	}
	if traceEndpoint != "otel-collector:4317" || metricEndpoint != "otel-collector:4317" {
		t.Fatalf("unexpected endpoints trace=%q metric=%q", traceEndpoint, metricEndpoint)
	}
	if !traceInsecure || !metricInsecure {
		t.Fatalf("expected insecure exporters, got trace=%v metric=%v", traceInsecure, metricInsecure)
	}
	if err := shutdown(context.Background()); err != nil {
		t.Fatalf("shutdown() error = %v", err)
	}
}

func TestSetupPropagatesExporterErrors(t *testing.T) {
	originalTrace := newTraceExporter
	originalMetric := newMetricReader
	t.Cleanup(func() {
		newTraceExporter = originalTrace
		newMetricReader = originalMetric
	})

	traceErr := errors.New("trace exporter boom")
	newTraceExporter = func(context.Context, string, bool) (sdktrace.SpanExporter, error) {
		return nil, traceErr
	}
	if _, err := Setup(context.Background(), "reasoning-engine", "otel-collector:4317"); !errors.Is(err, traceErr) {
		t.Fatalf("Setup() error = %v, want %v", err, traceErr)
	}

	newTraceExporter = func(context.Context, string, bool) (sdktrace.SpanExporter, error) {
		return fakeSpanExporter{}, nil
	}
	metricErr := errors.New("metric exporter boom")
	newMetricReader = func(context.Context, string, bool) (sdkmetric.Reader, error) {
		return nil, metricErr
	}
	if _, err := Setup(context.Background(), "reasoning-engine", "otel-collector:4317"); !errors.Is(err, metricErr) {
		t.Fatalf("Setup() error = %v, want %v", err, metricErr)
	}
}

func TestSetupPropagatesResourceMergeError(t *testing.T) {
	originalTrace := newTraceExporter
	originalMetric := newMetricReader
	originalMerge := mergeTelemetryResource
	t.Cleanup(func() {
		newTraceExporter = originalTrace
		newMetricReader = originalMetric
		mergeTelemetryResource = originalMerge
	})

	expectedErr := errors.New("merge boom")
	newTraceExporter = func(context.Context, string, bool) (sdktrace.SpanExporter, error) {
		return fakeSpanExporter{}, nil
	}
	newMetricReader = func(context.Context, string, bool) (sdkmetric.Reader, error) {
		return sdkmetric.NewManualReader(), nil
	}
	mergeTelemetryResource = func(*sdkresource.Resource, *sdkresource.Resource) (*sdkresource.Resource, error) {
		return nil, expectedErr
	}

	if _, err := Setup(context.Background(), "reasoning-engine", "otel-collector:4317"); !errors.Is(err, expectedErr) {
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
}
