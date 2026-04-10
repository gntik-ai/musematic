package grpcserver

import (
	"context"
	"io"
	"log/slog"
	"testing"

	simulationv1 "github.com/musematic/simulation-controller/api/grpc/v1"
	"github.com/stretchr/testify/require"
	"google.golang.org/grpc"
	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/status"
)

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

func TestRequestSimulationID(t *testing.T) {
	t.Parallel()

	require.Equal(t, "sim-1", requestSimulationID(&simulationv1.GetSimulationStatusRequest{SimulationId: "sim-1"}))
	require.Equal(t, "session-1", requestSimulationID(&simulationv1.CreateATERequest{SessionId: "session-1"}))
}
