package persistence

import (
	"context"
	"errors"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"

	"github.com/confluentinc/confluent-kafka-go/v2/kafka"
	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgconn"
	"github.com/stretchr/testify/require"
)

type fakeRow struct {
	scan func(dest ...any) error
}

func (f fakeRow) Scan(dest ...any) error {
	if f.scan != nil {
		return f.scan(dest...)
	}
	return nil
}

type fakeDB struct {
	exec func(ctx context.Context, sql string, args ...any) (pgconn.CommandTag, error)
	row  func(ctx context.Context, sql string, args ...any) pgx.Row
}

func (f fakeDB) Exec(ctx context.Context, sql string, args ...any) (pgconn.CommandTag, error) {
	if f.exec != nil {
		return f.exec(ctx, sql, args...)
	}
	return pgconn.NewCommandTag("INSERT 0 1"), nil
}

func (f fakeDB) QueryRow(ctx context.Context, sql string, args ...any) pgx.Row {
	if f.row != nil {
		return f.row(ctx, sql, args...)
	}
	return fakeRow{}
}

type fakeKafkaClient struct {
	produceErr error
	event      kafka.Event
	events     chan kafka.Event
	flushes    []int
	closed     int
	messages   []*kafka.Message
}

func (f *fakeKafkaClient) Produce(msg *kafka.Message, deliveryChan chan kafka.Event) error {
	f.messages = append(f.messages, msg)
	if f.produceErr != nil {
		return f.produceErr
	}
	if deliveryChan != nil && f.event != nil {
		deliveryChan <- f.event
	}
	return nil
}

func (f *fakeKafkaClient) Events() chan kafka.Event {
	if f.events == nil {
		f.events = make(chan kafka.Event)
	}
	return f.events
}

func (f *fakeKafkaClient) Flush(timeoutMs int) int {
	f.flushes = append(f.flushes, timeoutMs)
	return 0
}

func (f *fakeKafkaClient) Close() {
	f.closed++
	if f.events != nil {
		close(f.events)
	}
}

func TestNewPostgresPoolReturnsNilOnEmptyDSN(t *testing.T) {
	t.Parallel()
	require.Nil(t, NewPostgresPool(""))
}

func TestNewPostgresPoolPanicsOnInvalidDSN(t *testing.T) {
	t.Parallel()

	require.Panics(t, func() {
		_ = NewPostgresPool("://bad-dsn")
	})
}

func TestNewStoreExposesPool(t *testing.T) {
	t.Parallel()

	store := NewStore(nil)
	require.Nil(t, store.Pool())
}

func TestKafkaProducerNilIsNoop(t *testing.T) {
	t.Parallel()
	var producer *KafkaProducer
	require.NoError(t, producer.Produce("simulation.events", "sim-1", []byte("payload")))
}

func TestKafkaProducerEmptyBrokersReturnsNil(t *testing.T) {
	t.Parallel()

	require.Nil(t, NewKafkaProducer(""))
}

func TestNewKafkaProducerCreatesClient(t *testing.T) {
	t.Parallel()

	producer := NewKafkaProducer("127.0.0.1:9092")
	require.NotNil(t, producer)
	producer.Close()
}

func TestKafkaProducerProduceReturnsDeliveryError(t *testing.T) {
	t.Parallel()

	client := &fakeKafkaClient{
		event: &kafka.Message{TopicPartition: kafka.TopicPartition{Error: errors.New("delivery failed")}},
	}
	producer := &KafkaProducer{producer: client, deliveryTimeout: 10 * time.Millisecond}

	err := producer.Produce("simulation.events", "sim-1", []byte("payload"))
	require.EqualError(t, err, "delivery failed")
	require.Len(t, client.messages, 1)
	require.Equal(t, "simulation.events", *client.messages[0].TopicPartition.Topic)
	require.Equal(t, []byte("sim-1"), client.messages[0].Key)
}

func TestKafkaProducerProduceTimeoutReturnsNil(t *testing.T) {
	t.Parallel()

	producer := &KafkaProducer{producer: &fakeKafkaClient{}, deliveryTimeout: time.Nanosecond}
	require.NoError(t, producer.Produce("simulation.events", "sim-1", []byte("payload")))
}

func TestKafkaProducerCloseIsIdempotent(t *testing.T) {
	t.Parallel()

	client := &fakeKafkaClient{}
	producer := &KafkaProducer{producer: client}
	producer.Close()
	producer.Close()

	require.Equal(t, []int{5000}, client.flushes)
	require.Equal(t, 1, client.closed)
}

func TestMinIOClientPresignURLUsesBucketAndKey(t *testing.T) {
	t.Parallel()
	client := NewMinIOClient("minio.local:9000", "simulation-artifacts")
	require.Equal(t, "http://minio.local:9000/simulation-artifacts/sim-1/output.tar.gz", client.PresignGetURL("sim-1/output.tar.gz"))
}

func TestMinIOClientUploadSetsMetadataAndFailsOnBadStatus(t *testing.T) {
	t.Parallel()

	var gotPath string
	var gotMetadata string
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		gotPath = r.URL.Path
		gotMetadata = r.Header.Get("x-amz-meta-simulation-id")
		w.WriteHeader(http.StatusAccepted)
	}))
	defer server.Close()

	client := NewMinIOClient(server.URL, "simulation-artifacts")
	require.NoError(t, client.Upload(context.Background(), "sim-1/output.tar.gz", []byte("archive"), map[string]string{
		"x-amz-meta-simulation-id": "sim-1",
	}))
	require.Equal(t, "/simulation-artifacts/sim-1/output.tar.gz", gotPath)
	require.Equal(t, "sim-1", gotMetadata)

	errorServer := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		w.WriteHeader(http.StatusBadGateway)
	}))
	defer errorServer.Close()

	client = NewMinIOClient(errorServer.URL, "simulation-artifacts")
	err := client.Upload(context.Background(), "sim-1/output.tar.gz", []byte("archive"), nil)
	require.EqualError(t, err, "minio upload failed: 502 Bad Gateway")
}

func TestMinIOHelpersHandleNilAndSchemes(t *testing.T) {
	t.Parallel()

	var client *MinIOClient
	require.Equal(t, "", client.PresignGetURL("ignored"))
	require.Nil(t, NewMinIOClient("", "bucket"))
	require.Equal(t, "https://minio.local:9000", normaliseEndpoint("https://minio.local:9000/"))
}

func TestMapPGErrorConvertsUniqueViolations(t *testing.T) {
	t.Parallel()
	err := mapPGError(&pgconn.PgError{Code: "23505"})
	require.ErrorIs(t, err, ErrAlreadyExists)
}

func TestStoreMethodsRequireConfiguredDB(t *testing.T) {
	t.Parallel()

	store := &Store{}
	_, err := store.GetSimulation(context.Background(), "sim-1")
	require.EqualError(t, err, "postgres store is not configured")
	require.EqualError(t, store.InsertSimulation(context.Background(), SimulationRecord{}), "postgres store is not configured")
	require.EqualError(t, store.InsertSimulationArtifact(context.Background(), SimulationArtifactRecord{}), "postgres store is not configured")
	require.EqualError(t, store.InsertATESession(context.Background(), ATESessionRecord{}), "postgres store is not configured")
	require.EqualError(t, store.InsertATEResult(context.Background(), ATEResultRecord{}), "postgres store is not configured")
	require.EqualError(t, store.UpdateSimulationStatus(context.Background(), "sim-1", SimulationStatusUpdate{}), "postgres store is not configured")
	require.EqualError(t, store.UpdateATEReport(context.Background(), "session-1", "object", time.Now().UTC()), "postgres store is not configured")
	_, err = store.FindATESessionIDBySimulation(context.Background(), "sim-1")
	require.EqualError(t, err, "postgres store is not configured")
}

func TestStoreInsertSimulationMapsUniqueViolation(t *testing.T) {
	t.Parallel()

	store := &Store{db: fakeDB{
		exec: func(context.Context, string, ...any) (pgconn.CommandTag, error) {
			return pgconn.CommandTag{}, &pgconn.PgError{Code: "23505"}
		},
	}}

	err := store.InsertSimulation(context.Background(), SimulationRecord{SimulationID: "sim-1"})
	require.ErrorIs(t, err, ErrAlreadyExists)
}

func TestStoreUpdateSimulationStatusNotFound(t *testing.T) {
	t.Parallel()

	store := &Store{db: fakeDB{
		exec: func(context.Context, string, ...any) (pgconn.CommandTag, error) {
			return pgconn.NewCommandTag("UPDATE 0"), nil
		},
	}}

	err := store.UpdateSimulationStatus(context.Background(), "sim-1", SimulationStatusUpdate{Status: "FAILED"})
	require.ErrorIs(t, err, ErrNotFound)
}

func TestStoreGetSimulationMapsRows(t *testing.T) {
	t.Parallel()

	now := time.Now().UTC()
	started := now.Add(time.Minute)
	completed := started.Add(time.Minute)
	terminated := completed.Add(time.Minute)
	store := &Store{db: fakeDB{
		row: func(context.Context, string, ...any) pgx.Row {
			return fakeRow{scan: func(dest ...any) error {
				*dest[0].(*string) = "sim-1"
				*dest[1].(*string) = "busybox:latest"
				*dest[2].(*[]byte) = []byte(`{}`)
				*dest[3].(*string) = "COMPLETED"
				*dest[4].(*string) = "platform-simulation"
				*dest[5].(*string) = "pod-1"
				*dest[6].(*string) = "250m"
				*dest[7].(*string) = "256Mi"
				*dest[8].(*int32) = 120
				*dest[9].(*time.Time) = now
				*dest[10].(**time.Time) = &started
				*dest[11].(**time.Time) = &completed
				*dest[12].(**time.Time) = &terminated
				*dest[13].(*string) = ""
				return nil
			}}
		},
	}}

	record, err := store.GetSimulation(context.Background(), "sim-1")
	require.NoError(t, err)
	require.Equal(t, "sim-1", record.SimulationID)
	require.Equal(t, "pod-1", record.PodName)
	require.NotNil(t, record.StartedAt)
	require.NotNil(t, record.CompletedAt)
	require.NotNil(t, record.TerminatedAt)
}

func TestStoreGetSimulationMapsNotFound(t *testing.T) {
	t.Parallel()

	store := &Store{db: fakeDB{
		row: func(context.Context, string, ...any) pgx.Row {
			return fakeRow{scan: func(dest ...any) error { return pgx.ErrNoRows }}
		},
	}}

	_, err := store.GetSimulation(context.Background(), "missing")
	require.ErrorIs(t, err, ErrNotFound)
}

func TestStoreInsertAndLookupATESessionRecords(t *testing.T) {
	t.Parallel()

	execCalls := 0
	store := &Store{db: fakeDB{
		exec: func(context.Context, string, ...any) (pgconn.CommandTag, error) {
			execCalls++
			return pgconn.NewCommandTag("INSERT 0 1"), nil
		},
		row: func(context.Context, string, ...any) pgx.Row {
			return fakeRow{scan: func(dest ...any) error {
				*dest[0].(*string) = "session-1"
				return nil
			}}
		},
	}}

	require.NoError(t, store.InsertSimulationArtifact(context.Background(), SimulationArtifactRecord{SimulationID: "sim-1"}))
	require.NoError(t, store.InsertATESession(context.Background(), ATESessionRecord{SessionID: "session-1"}))
	require.NoError(t, store.InsertATEResult(context.Background(), ATEResultRecord{SessionID: "session-1", ScenarioID: "scenario-1"}))
	require.NoError(t, store.UpdateATEReport(context.Background(), "session-1", "sim-1/report.json", time.Now().UTC()))

	sessionID, err := store.FindATESessionIDBySimulation(context.Background(), "sim-1")
	require.NoError(t, err)
	require.Equal(t, "session-1", sessionID)
	require.Equal(t, 4, execCalls)
}

func TestStoreLookupAndUpdateATESessionHandleNotFound(t *testing.T) {
	t.Parallel()

	store := &Store{db: fakeDB{
		exec: func(context.Context, string, ...any) (pgconn.CommandTag, error) {
			return pgconn.NewCommandTag("UPDATE 0"), nil
		},
		row: func(context.Context, string, ...any) pgx.Row {
			return fakeRow{scan: func(dest ...any) error { return pgx.ErrNoRows }}
		},
	}}

	_, err := store.FindATESessionIDBySimulation(context.Background(), "missing")
	require.ErrorIs(t, err, ErrNotFound)
	require.ErrorIs(t, store.UpdateATEReport(context.Background(), "missing", "report", time.Now().UTC()), ErrNotFound)
}
