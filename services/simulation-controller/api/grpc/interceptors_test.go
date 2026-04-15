package grpcserver

import (
	"context"
	"errors"
	"io"
	"log/slog"
	"testing"

	simulationv1 "github.com/musematic/simulation-controller/api/grpc/v1"
	"github.com/stretchr/testify/require"
	"google.golang.org/grpc"
	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/metadata"
	"google.golang.org/grpc/status"
)

type fakeServerStream struct {
	ctx context.Context
}

func (f fakeServerStream) SetHeader(metadata.MD) error  { return nil }
func (f fakeServerStream) SendHeader(metadata.MD) error { return nil }
func (f fakeServerStream) SetTrailer(metadata.MD)       {}
func (f fakeServerStream) Context() context.Context {
	if f.ctx != nil {
		return f.ctx
	}
	return context.Background()
}
func (f fakeServerStream) SendMsg(any) error { return nil }
func (f fakeServerStream) RecvMsg(any) error { return nil }

func TestUnaryInterceptorRecoversPanic(t *testing.T) {
	t.Parallel()

	logger := slog.New(slog.NewTextHandler(io.Discard, nil))
	interceptor := UnaryInterceptor(logger)
	_, err := interceptor(
		context.Background(),
		&simulationv1.GetSimulationStatusRequest{SimulationId: "sim-1"},
		&grpc.UnaryServerInfo{FullMethod: "/musematic.simulation.v1.SimulationControlService/GetSimulationStatus"},
		func(context.Context, any) (any, error) {
			panic("boom")
		},
	)

	require.Error(t, err)
	statusValue, ok := status.FromError(err)
	require.True(t, ok)
	require.Equal(t, codes.Internal, statusValue.Code())
}

func TestInterceptorsPassThroughAndStreamRecoversPanic(t *testing.T) {
	t.Parallel()

	logger := slog.New(slog.NewTextHandler(io.Discard, nil))
	unary := UnaryInterceptor(logger)
	response, err := unary(
		context.Background(),
		&simulationv1.CreateSimulationRequest{SimulationId: "sim-1"},
		&grpc.UnaryServerInfo{FullMethod: simulationv1.SimulationControlService_CreateSimulation_FullMethodName},
		func(context.Context, any) (any, error) {
			return "ok", nil
		},
	)
	require.NoError(t, err)
	require.Equal(t, "ok", response)

	stream := StreamInterceptor(logger)
	require.EqualError(t, stream(nil, fakeServerStream{}, &grpc.StreamServerInfo{FullMethod: "method"}, func(any, grpc.ServerStream) error {
		return errors.New("stream failed")
	}), "stream failed")

	err = stream(nil, fakeServerStream{}, &grpc.StreamServerInfo{FullMethod: "method"}, func(any, grpc.ServerStream) error {
		panic("boom")
	})
	require.Equal(t, codes.Internal, status.Code(err))
}

func TestRequestSimulationID(t *testing.T) {
	t.Parallel()

	require.Equal(t, "sim-1", requestSimulationID(&simulationv1.CreateSimulationRequest{SimulationId: "sim-1"}))
	require.Equal(t, "sim-1", requestSimulationID(&simulationv1.GetSimulationStatusRequest{SimulationId: "sim-1"}))
	require.Equal(t, "sim-1", requestSimulationID(&simulationv1.TerminateSimulationRequest{SimulationId: "sim-1"}))
	require.Equal(t, "sim-1", requestSimulationID(&simulationv1.CollectSimulationArtifactsRequest{SimulationId: "sim-1"}))
	require.Equal(t, "session-1", requestSimulationID(&simulationv1.CreateATERequest{SessionId: "session-1"}))
	require.Empty(t, requestSimulationID(struct{}{}))
}
