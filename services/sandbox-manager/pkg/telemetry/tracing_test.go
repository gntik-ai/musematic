package telemetry

import (
	"context"
	"errors"
	"testing"

	sdkmetric "go.opentelemetry.io/otel/sdk/metric"
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
	originalMetric := newMetricReader
	originalMerge := mergeTelemetryResource
	t.Cleanup(func() {
		newTraceExporter = originalExporter
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
		return fakeExporter{}, nil
	}
	newMetricReader = func(_ context.Context, endpoint string, insecure bool) (sdkmetric.Reader, error) {
		metricEndpoint = endpoint
		metricInsecure = insecure
		return sdkmetric.NewManualReader(), nil
	}
	mergeTelemetryResource = sdkresource.Merge

	shutdown, err := Setup(context.Background(), "sandbox-manager", "http://otel-collector:4317")
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

func TestSetupWithSecureEndpointOmitsInsecureOption(t *testing.T) {
	originalExporter := newTraceExporter
	originalMetric := newMetricReader
	originalMerge := mergeTelemetryResource
	t.Cleanup(func() {
		newTraceExporter = originalExporter
		newMetricReader = originalMetric
		mergeTelemetryResource = originalMerge
	})

	var traceInsecure bool
	var metricInsecure bool
	newTraceExporter = func(_ context.Context, _ string, insecure bool) (sdktrace.SpanExporter, error) {
		traceInsecure = insecure
		return fakeExporter{}, nil
	}
	newMetricReader = func(_ context.Context, _ string, insecure bool) (sdkmetric.Reader, error) {
		metricInsecure = insecure
		return sdkmetric.NewManualReader(), nil
	}
	mergeTelemetryResource = sdkresource.Merge

	if _, err := Setup(context.Background(), "sandbox-manager", "https://otel-collector:4317"); err != nil {
		t.Fatalf("Setup() error = %v", err)
	}
	if traceInsecure || metricInsecure {
		t.Fatalf("expected secure exporters, got trace=%v metric=%v", traceInsecure, metricInsecure)
	}
}

func TestSetupPropagatesExporterError(t *testing.T) {
	originalExporter := newTraceExporter
	originalMetric := newMetricReader
	t.Cleanup(func() {
		newTraceExporter = originalExporter
		newMetricReader = originalMetric
	})

	expectedErr := errors.New("exporter boom")
	newTraceExporter = func(context.Context, string, bool) (sdktrace.SpanExporter, error) {
		return nil, expectedErr
	}

	if _, err := Setup(context.Background(), "sandbox-manager", "otel-collector:4317"); !errors.Is(err, expectedErr) {
		t.Fatalf("Setup() error = %v, want %v", err, expectedErr)
	}

	newTraceExporter = func(context.Context, string, bool) (sdktrace.SpanExporter, error) {
		return fakeExporter{}, nil
	}
	newMetricReader = func(context.Context, string, bool) (sdkmetric.Reader, error) {
		return nil, expectedErr
	}
	if _, err := Setup(context.Background(), "sandbox-manager", "otel-collector:4317"); !errors.Is(err, expectedErr) {
		t.Fatalf("Setup() error = %v, want %v", err, expectedErr)
	}
}

func TestSetupPropagatesResourceMergeError(t *testing.T) {
	originalExporter := newTraceExporter
	originalMetric := newMetricReader
	originalMerge := mergeTelemetryResource
	t.Cleanup(func() {
		newTraceExporter = originalExporter
		newMetricReader = originalMetric
		mergeTelemetryResource = originalMerge
	})

	expectedErr := errors.New("merge boom")
	newTraceExporter = func(context.Context, string, bool) (sdktrace.SpanExporter, error) {
		return fakeExporter{}, nil
	}
	newMetricReader = func(context.Context, string, bool) (sdkmetric.Reader, error) {
		return sdkmetric.NewManualReader(), nil
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
