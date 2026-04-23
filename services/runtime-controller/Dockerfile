ARG GO_BASE=mirror.gcr.io/library/golang:1.25-alpine3.23
ARG ALPINE_BASE=mirror.gcr.io/library/alpine:3.23.3

FROM ${GO_BASE} AS builder

RUN apk add --no-cache build-base pkgconf

WORKDIR /src
COPY go.mod go.sum* ./
RUN go mod download || true
COPY . .
ENV CGO_ENABLED=1 GOOS=linux GOARCH=amd64
RUN go build -tags musl -ldflags="-s -w" -o /runtime-controller ./cmd/runtime-controller

FROM ${ALPINE_BASE}

RUN apk upgrade --no-cache \
    && apk add --no-cache ca-certificates libstdc++ \
    && addgroup -S app \
    && adduser -S -G app -u 65532 nonroot

COPY --from=builder /runtime-controller /runtime-controller
USER nonroot
ENTRYPOINT ["/runtime-controller"]
