PROTO_DIR := proto
PROTO_FILE := $(PROTO_DIR)/sandbox_manager.proto
GOPATH_BIN := $(shell go env GOPATH 2>/dev/null)/bin

.PHONY: check-proto-tools proto build test test-integration lint image helm-lint

check-proto-tools:
	@command -v protoc >/dev/null 2>&1 || { \
		echo "missing protoc; install Protocol Buffers compiler first"; \
		exit 1; \
	}
	@PATH="$(GOPATH_BIN):$$PATH"; command -v protoc-gen-go >/dev/null 2>&1 || { \
		echo "missing protoc-gen-go; install with:"; \
		echo "  go install google.golang.org/protobuf/cmd/protoc-gen-go@latest"; \
		exit 1; \
	}
	@PATH="$(GOPATH_BIN):$$PATH"; command -v protoc-gen-go-grpc >/dev/null 2>&1 || { \
		echo "missing protoc-gen-go-grpc; install with:"; \
		echo "  go install google.golang.org/grpc/cmd/protoc-gen-go-grpc@latest"; \
		exit 1; \
	}

proto: check-proto-tools
	PATH="$(GOPATH_BIN):$$PATH" protoc --go_out=./api/grpc/v1 --go_opt=paths=source_relative \
		--go-grpc_out=./api/grpc/v1 --go-grpc_opt=paths=source_relative \
		-I $(PROTO_DIR) $(PROTO_FILE)

build:
	GOCACHE=/tmp/sandbox-manager-gocache go build ./cmd/sandbox-manager

test:
	GOCACHE=/tmp/sandbox-manager-gocache go test ./... -coverprofile=coverage.out

test-integration:
	GOCACHE=/tmp/sandbox-manager-gocache go test ./... -tags=integration -v -timeout 120s

lint:
	golangci-lint run

image:
	docker build -t ghcr.io/andrea-mucci/musematic/sandbox-manager:latest .

helm-lint:
	helm lint deploy/helm/sandbox-manager
