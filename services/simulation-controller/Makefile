PROTO_DIR := proto
PROTO_FILE := $(PROTO_DIR)/simulation_controller.proto
GOPATH_BIN := $(shell go env GOPATH 2>/dev/null)/bin

.PHONY: check-proto-tools proto build test test-integration lint docker

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
	GOCACHE=/tmp/simulation-controller-gocache go build ./cmd/simulation-controller

test:
	GOCACHE=/tmp/simulation-controller-gocache go test ./...

test-integration:
	GOCACHE=/tmp/simulation-controller-gocache go test ./... -tags=integration -v -timeout 120s

lint:
	golangci-lint run

docker:
	docker build -t musematic/simulation-controller:latest .
