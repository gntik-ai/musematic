FROM golang:1.22-alpine AS builder

WORKDIR /src
COPY go.mod go.sum ./
RUN go mod download || true
COPY . .
ENV CGO_ENABLED=0 GOOS=linux GOARCH=amd64
RUN go build -ldflags="-s -w" -o /reasoning-engine ./cmd/reasoning-engine/

FROM gcr.io/distroless/static:nonroot

COPY --from=builder /reasoning-engine /reasoning-engine
EXPOSE 50052
USER nonroot:nonroot
ENTRYPOINT ["/reasoning-engine"]
