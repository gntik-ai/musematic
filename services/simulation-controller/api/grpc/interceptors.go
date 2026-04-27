package grpcserver

import (
	"context"
	"log/slog"

	simulationv1 "github.com/musematic/simulation-controller/api/grpc/v1"
	structuredlogging "github.com/musematic/simulation-controller/internal/logging"
	"google.golang.org/grpc"
	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/status"
)

func UnaryInterceptor(logger *slog.Logger) grpc.UnaryServerInterceptor {
	return func(ctx context.Context, req any, info *grpc.UnaryServerInfo, handler grpc.UnaryHandler) (resp any, err error) {
		ctx = structuredlogging.WithGRPCMetadata(ctx)
		defer func() {
			if recovered := recover(); recovered != nil {
				if logger != nil {
					logger.Error("panic recovered", "method", info.FullMethod, "panic", recovered)
				}
				resp = nil
				err = status.Error(codes.Internal, "internal server error")
			}
		}()
		if logger != nil {
			logger.InfoContext(ctx, "grpc unary request", "method", info.FullMethod, "simulation_id", requestSimulationID(req))
		}
		return handler(ctx, req)
	}
}

func StreamInterceptor(logger *slog.Logger) grpc.StreamServerInterceptor {
	return func(srv any, ss grpc.ServerStream, info *grpc.StreamServerInfo, handler grpc.StreamHandler) (err error) {
		wrapped := metadataServerStream{ServerStream: ss, ctx: structuredlogging.WithGRPCMetadata(ss.Context())}
		defer func() {
			if recovered := recover(); recovered != nil {
				if logger != nil {
					logger.Error("panic recovered", "method", info.FullMethod, "panic", recovered)
				}
				err = status.Error(codes.Internal, "internal server error")
			}
		}()
		if logger != nil {
			logger.InfoContext(wrapped.Context(), "grpc stream request", "method", info.FullMethod)
		}
		return handler(srv, wrapped)
	}
}

type metadataServerStream struct {
	grpc.ServerStream
	ctx context.Context
}

func (s metadataServerStream) Context() context.Context {
	return s.ctx
}

func requestSimulationID(req any) string {
	switch typed := req.(type) {
	case *simulationv1.CreateSimulationRequest:
		return typed.GetSimulationId()
	case *simulationv1.GetSimulationStatusRequest:
		return typed.GetSimulationId()
	case *simulationv1.TerminateSimulationRequest:
		return typed.GetSimulationId()
	case *simulationv1.CollectSimulationArtifactsRequest:
		return typed.GetSimulationId()
	case *simulationv1.CreateATERequest:
		return typed.GetSessionId()
	default:
		return ""
	}
}
