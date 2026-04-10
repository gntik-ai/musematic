package reasoningv1

import (
	"context"
	"log/slog"

	"go.opentelemetry.io/contrib/instrumentation/google.golang.org/grpc/otelgrpc"
	"google.golang.org/grpc"
	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/status"
)

func UnaryInterceptor(logger *slog.Logger) grpc.UnaryServerInterceptor {
	otelInterceptor := otelgrpc.UnaryServerInterceptor()

	return func(ctx context.Context, req any, info *grpc.UnaryServerInfo, handler grpc.UnaryHandler) (resp any, err error) {
		wrapped := func(innerCtx context.Context, innerReq any) (response any, innerErr error) {
			defer func() {
				if recovered := recover(); recovered != nil {
					if logger != nil {
						logger.Error("panic recovered", "method", info.FullMethod, "panic", recovered)
					}
					response = nil
					innerErr = status.Error(codes.Internal, "internal server error")
				}
			}()
			if logger != nil {
				logger.Info("grpc unary request", "method", info.FullMethod)
			}
			return handler(innerCtx, innerReq)
		}

		return otelInterceptor(ctx, req, info, wrapped)
	}
}

func StreamInterceptor(logger *slog.Logger) grpc.StreamServerInterceptor {
	otelInterceptor := otelgrpc.StreamServerInterceptor()

	return func(srv any, ss grpc.ServerStream, info *grpc.StreamServerInfo, handler grpc.StreamHandler) (err error) {
		wrapped := func(innerSrv any, innerStream grpc.ServerStream) (innerErr error) {
			defer func() {
				if recovered := recover(); recovered != nil {
					if logger != nil {
						logger.Error("panic recovered", "method", info.FullMethod, "panic", recovered)
					}
					innerErr = status.Error(codes.Internal, "internal server error")
				}
			}()
			if logger != nil {
				logger.Info("grpc stream request", "method", info.FullMethod)
			}
			return handler(innerSrv, innerStream)
		}

		return otelInterceptor(srv, ss, info, wrapped)
	}
}
