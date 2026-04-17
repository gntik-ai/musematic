package telemetry

import (
	"context"
	"strings"

	"go.opentelemetry.io/otel"
	"go.opentelemetry.io/otel/exporters/otlp/otlpmetric/otlpmetricgrpc"
	"go.opentelemetry.io/otel/exporters/otlp/otlptrace/otlptracegrpc"
	"go.opentelemetry.io/otel/propagation"
	sdkresource "go.opentelemetry.io/otel/sdk/resource"
	sdkmetric "go.opentelemetry.io/otel/sdk/metric"
	sdktrace "go.opentelemetry.io/otel/sdk/trace"
	semconv "go.opentelemetry.io/otel/semconv/v1.37.0"
)

type Shutdown func(context.Context) error

var (
	newTraceExporter = func(ctx context.Context, endpoint string, insecure bool) (sdktrace.SpanExporter, error) {
		opts := []otlptracegrpc.Option{otlptracegrpc.WithEndpoint(endpoint)}
		if insecure {
			opts = append(opts, otlptracegrpc.WithInsecure())
		}
		return otlptracegrpc.New(ctx, opts...)
	}
	newMetricReader = func(ctx context.Context, endpoint string, insecure bool) (sdkmetric.Reader, error) {
		opts := []otlpmetricgrpc.Option{otlpmetricgrpc.WithEndpoint(endpoint)}
		if insecure {
			opts = append(opts, otlpmetricgrpc.WithInsecure())
		}
		exporter, err := otlpmetricgrpc.New(ctx, opts...)
		if err != nil {
			return nil, err
		}
		return sdkmetric.NewPeriodicReader(exporter), nil
	}
	mergeTelemetryResource = sdkresource.Merge
)

func Setup(ctx context.Context, serviceName string, endpoint string) (Shutdown, error) {
	trimmed := strings.TrimSpace(endpoint)
	if trimmed == "" {
		return func(context.Context) error { return nil }, nil
	}

	normalisedEndpoint := normaliseEndpoint(trimmed)
	insecure := !strings.HasPrefix(strings.ToLower(trimmed), "https://")

	traceExporter, err := newTraceExporter(ctx, normalisedEndpoint, insecure)
	if err != nil {
		return nil, err
	}
	metricReader, err := newMetricReader(ctx, normalisedEndpoint, insecure)
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

	tracerProvider := sdktrace.NewTracerProvider(
		sdktrace.WithBatcher(traceExporter),
		sdktrace.WithResource(res),
	)
	meterProvider := sdkmetric.NewMeterProvider(
		sdkmetric.WithResource(res),
		sdkmetric.WithReader(metricReader),
	)
	otel.SetTracerProvider(tracerProvider)
	otel.SetMeterProvider(meterProvider)
	otel.SetTextMapPropagator(propagation.NewCompositeTextMapPropagator(
		propagation.TraceContext{},
		propagation.Baggage{},
	))

	return func(shutdownCtx context.Context) error {
		var shutdownErr error
		if err := meterProvider.Shutdown(shutdownCtx); err != nil && shutdownErr == nil {
			shutdownErr = err
		}
		if err := tracerProvider.Shutdown(shutdownCtx); err != nil && shutdownErr == nil {
			shutdownErr = err
		}
		return shutdownErr
	}, nil
}

func normaliseEndpoint(endpoint string) string {
	trimmed := strings.TrimSpace(endpoint)
	trimmed = strings.TrimPrefix(trimmed, "http://")
	trimmed = strings.TrimPrefix(trimmed, "https://")
	return trimmed
}
