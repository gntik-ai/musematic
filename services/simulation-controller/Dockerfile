FROM golang:1.22-alpine AS builder

WORKDIR /src
COPY go.mod go.sum* ./
RUN go mod download

COPY . .
RUN CGO_ENABLED=0 GOOS=linux GOARCH=amd64 go build -o /simulation-controller ./cmd/simulation-controller

FROM gcr.io/distroless/static:nonroot

COPY --from=builder /simulation-controller /simulation-controller
EXPOSE 50055
USER nonroot:nonroot
ENTRYPOINT ["/simulation-controller"]
