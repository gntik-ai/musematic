PROTO_DIR := proto
PROTO_FILE := $(PROTO_DIR)/runtime_controller.proto
GOPATH_BIN := $(shell go env GOPATH 2>/dev/null)/bin
COVERAGE_EXCLUDE_RE := /api/grpc/v1$$|/cmd/runtime-controller$$|/internal/state$$|/pkg/k8s$$

.PHONY: check-proto-tools proto test test-integration build docker-build coverage

check-proto-tools:
	@command -v protoc >/dev/null 2>&1 || { \
		echo "missing protoc; install Protocol Buffers compiler first"; \
		exit 1; \
	}
	@PATH="$(GOPATH_BIN):$$PATH"; command -v protoc-gen-go >/dev/null 2>&1 || { \
		echo "missing protoc-gen-go; install with:"; \
		echo "  go install google.golang.org/protobuf/cmd/protoc-gen-go@latest"; \
		echo "and ensure $(GOPATH_BIN) is on PATH"; \
		exit 1; \
	}
	@PATH="$(GOPATH_BIN):$$PATH"; command -v protoc-gen-go-grpc >/dev/null 2>&1 || { \
		echo "missing protoc-gen-go-grpc; install with:"; \
		echo "  go install google.golang.org/grpc/cmd/protoc-gen-go-grpc@latest"; \
		echo "and ensure $(GOPATH_BIN) is on PATH"; \
		exit 1; \
	}

proto: check-proto-tools
	PATH="$(GOPATH_BIN):$$PATH" protoc --go_out=./api/grpc/v1 --go_opt=paths=source_relative \
		--go-grpc_out=./api/grpc/v1 --go-grpc_opt=paths=source_relative \
		-I $(PROTO_DIR) $(PROTO_FILE)

test:
	GOCACHE=/tmp/runtime-controller-gocache go test ./...

test-integration:
	GOCACHE=/tmp/runtime-controller-gocache go test ./... -tags=integration -v -timeout 120s

build:
	GOCACHE=/tmp/runtime-controller-gocache go build ./cmd/runtime-controller

docker-build:
	docker build -t ghcr.io/andrea-mucci/musematic/runtime-controller:latest .

coverage:
	@packages="$$(GOCACHE=/tmp/runtime-controller-gocache GOPATH=$(shell go env GOPATH 2>/dev/null) go list ./... | grep -Ev '$(COVERAGE_EXCLUDE_RE)')"; \
	coverpkg="$$(printf '%s\n' "$$packages" | paste -sd, -)"; \
	GOCACHE=/tmp/runtime-controller-gocache GOPATH=$(shell go env GOPATH 2>/dev/null) go test $$packages -coverpkg="$$coverpkg" -coverprofile=coverage.out; \
	GOCACHE=/tmp/runtime-controller-gocache go tool cover -func=coverage.out
