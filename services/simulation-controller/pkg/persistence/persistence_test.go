package persistence

import (
	"testing"

	"github.com/jackc/pgx/v5/pgconn"
	"github.com/stretchr/testify/require"
)

func TestNewPostgresPoolReturnsNilOnEmptyDSN(t *testing.T) {
	t.Parallel()
	require.Nil(t, NewPostgresPool(""))
}

func TestKafkaProducerNilIsNoop(t *testing.T) {
	t.Parallel()
	var producer *KafkaProducer
	require.NoError(t, producer.Produce("simulation.events", "sim-1", []byte("payload")))
}

func TestMinIOClientPresignURLUsesBucketAndKey(t *testing.T) {
	t.Parallel()
	client := NewMinIOClient("minio.local:9000", "simulation-artifacts")
	require.Equal(t, "http://minio.local:9000/simulation-artifacts/sim-1/output.tar.gz", client.PresignGetURL("sim-1/output.tar.gz"))
}

func TestMapPGErrorConvertsUniqueViolations(t *testing.T) {
	t.Parallel()
	err := mapPGError(&pgconn.PgError{Code: "23505"})
	require.ErrorIs(t, err, ErrAlreadyExists)
}
