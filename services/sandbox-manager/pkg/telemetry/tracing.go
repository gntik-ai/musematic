package telemetry

import (
	"context"
	"strings"

	"go.opentelemetry.io/otel"
	"go.opentelemetry.io/otel/exporters/otlp/otlptrace/otlptracegrpc"
	"go.opentelemetry.io/otel/propagation"
	sdkresource "go.opentelemetry.io/otel/sdk/resource"
	sdktrace "go.opentelemetry.io/otel/sdk/trace"
	semconv "go.opentelemetry.io/otel/semconv/v1.26.0"
)

type Shutdown func(context.Context) error

var (
	newTraceExporter = func(ctx context.Context, opts ...otlptracegrpc.Option) (sdktrace.SpanExporter, error) {
		return otlptracegrpc.New(ctx, opts...)
	}
	mergeTelemetryResource = sdkresource.Merge
)

func Setup(ctx context.Context, serviceName string, endpoint string) (Shutdown, error) {
	if strings.TrimSpace(endpoint) == "" {
		return func(context.Context) error { return nil }, nil
	}

	opts := []otlptracegrpc.Option{
		otlptracegrpc.WithEndpoint(normaliseEndpoint(endpoint)),
	}
	if !strings.HasPrefix(strings.ToLower(strings.TrimSpace(endpoint)), "https://") {
		opts = append(opts, otlptracegrpc.WithInsecure())
	}

	exporter, err := newTraceExporter(ctx, opts...)
	if err != nil {
		return nil, err
	}

	res, err := mergeTelemetryResource(
		sdkresource.Default(),
		sdkresource.NewWithAttributes(
			semconv.SchemaURL,
			semconv.ServiceName(serviceName),
		),
	)
	if err != nil {
		return nil, err
	}

	provider := sdktrace.NewTracerProvider(
		sdktrace.WithBatcher(exporter),
		sdktrace.WithResource(res),
	)
	otel.SetTracerProvider(provider)
	otel.SetTextMapPropagator(propagation.NewCompositeTextMapPropagator(
		propagation.TraceContext{},
		propagation.Baggage{},
	))

	return provider.Shutdown, nil
}

func normaliseEndpoint(endpoint string) string {
	trimmed := strings.TrimSpace(endpoint)
	trimmed = strings.TrimPrefix(trimmed, "http://")
	trimmed = strings.TrimPrefix(trimmed, "https://")
	return trimmed
}
