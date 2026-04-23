ARG GO_BASE=mirror.gcr.io/library/golang:1.25-alpine3.23
ARG ALPINE_BASE=mirror.gcr.io/library/alpine:3.23.3

FROM ${GO_BASE} AS builder

RUN apk add --no-cache build-base pkgconf

WORKDIR /src
COPY go.mod go.sum* ./
RUN go mod download || true
COPY . .
RUN CGO_ENABLED=1 GOARCH=amd64 GOOS=linux go build -tags musl -ldflags="-s -w" -o /sandbox-manager ./cmd/sandbox-manager

FROM ${ALPINE_BASE}

RUN apk upgrade --no-cache \
    && apk add --no-cache ca-certificates libstdc++ \
    && addgroup -S app \
    && adduser -S -G app -u 65532 nonroot

COPY --from=builder /sandbox-manager /sandbox-manager
USER nonroot
ENTRYPOINT ["/sandbox-manager"]
