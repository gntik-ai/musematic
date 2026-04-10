class KafkaProducerError(Exception):
    """Raised when Kafka producer delivery fails."""


class KafkaConsumerError(Exception):
    """Raised when Kafka consumer operations fail."""


class ObjectStorageError(Exception):
    """Raised when object storage operations fail."""


class ObjectNotFoundError(ObjectStorageError):
    """Raised when an object key or version cannot be found."""


class BucketNotFoundError(ObjectStorageError):
    """Raised when a target bucket does not exist."""


class QdrantError(Exception):
    """Raised when Qdrant operations fail."""


class Neo4jClientError(Exception):
    """Raised when Neo4j client operations fail."""


class Neo4jConstraintViolationError(Neo4jClientError):
    """Raised when a Neo4j uniqueness or schema constraint is violated."""


class Neo4jNodeNotFoundError(Neo4jClientError):
    """Raised when a referenced Neo4j node does not exist."""


class Neo4jConnectionError(Neo4jClientError):
    """Raised when the Neo4j driver cannot connect to the database."""


class HopLimitExceededError(Neo4jClientError):
    """Raised when local graph mode is asked to traverse beyond the supported hop limit."""
