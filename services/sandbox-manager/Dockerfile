FROM golang:1.22-alpine AS builder

WORKDIR /src
COPY . .
RUN CGO_ENABLED=0 GOARCH=amd64 GOOS=linux go build -ldflags="-s -w" -o /sandbox-manager ./cmd/sandbox-manager

FROM gcr.io/distroless/static-debian12

COPY --from=builder /sandbox-manager /sandbox-manager
ENTRYPOINT ["/sandbox-manager"]
