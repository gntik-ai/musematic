package reasoningv1

import (
	"context"
	"log/slog"

	"google.golang.org/grpc"
	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/status"
)

func UnaryInterceptor(logger *slog.Logger) grpc.UnaryServerInterceptor {
	return func(ctx context.Context, req any, info *grpc.UnaryServerInfo, handler grpc.UnaryHandler) (resp any, err error) {
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
			logger.Info("grpc unary request", "method", info.FullMethod)
		}
		return handler(ctx, req)
	}
}

func StreamInterceptor(logger *slog.Logger) grpc.StreamServerInterceptor {
	return func(srv any, ss grpc.ServerStream, info *grpc.StreamServerInfo, handler grpc.StreamHandler) (err error) {
		defer func() {
			if recovered := recover(); recovered != nil {
				if logger != nil {
					logger.Error("panic recovered", "method", info.FullMethod, "panic", recovered)
				}
				err = status.Error(codes.Internal, "internal server error")
			}
		}()
		if logger != nil {
			logger.Info("grpc stream request", "method", info.FullMethod)
		}
		return handler(srv, ss)
	}
}
