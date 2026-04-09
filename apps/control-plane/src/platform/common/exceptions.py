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
