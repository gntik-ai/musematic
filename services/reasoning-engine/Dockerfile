FROM golang:1.25-alpine3.23 AS builder

RUN apk add --no-cache build-base pkgconf

WORKDIR /src
COPY go.mod go.sum ./
RUN go mod download || true
COPY . .
ENV CGO_ENABLED=1 GOOS=linux GOARCH=amd64
RUN go build -tags musl -ldflags="-s -w" -o /reasoning-engine ./cmd/reasoning-engine/

FROM alpine:3.23.3

RUN apk upgrade --no-cache \
    && apk add --no-cache ca-certificates libstdc++ \
    && addgroup -S app \
    && adduser -S -G app -u 65532 nonroot

COPY --from=builder /reasoning-engine /reasoning-engine
EXPOSE 50052
USER nonroot
ENTRYPOINT ["/reasoning-engine"]
