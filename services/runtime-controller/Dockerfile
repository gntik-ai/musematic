FROM golang:1.22-alpine AS builder

WORKDIR /src
COPY go.mod go.sum* ./
RUN go mod download || true
COPY . .
ENV CGO_ENABLED=0 GOOS=linux GOARCH=amd64
RUN go build -ldflags="-s -w" -o /runtime-controller ./cmd/runtime-controller

FROM gcr.io/distroless/static-debian12

COPY --from=builder /runtime-controller /runtime-controller
COPY --from=builder /etc/ssl/certs/ca-certificates.crt /etc/ssl/certs/ca-certificates.crt
USER nonroot:nonroot
ENTRYPOINT ["/runtime-controller"]
