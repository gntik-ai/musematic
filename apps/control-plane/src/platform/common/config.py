from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore")

    NEO4J_URL: str | None = None
    NEO4J_MAX_CONNECTION_POOL_SIZE: int = 50
    GRAPH_MODE: str = "auto"
    KAFKA_BOOTSTRAP_SERVERS: str = "localhost:9092"
    KAFKA_CONSUMER_GROUP_ID: str = "platform-control"
    MINIO_ENDPOINT: str = "http://musematic-minio.platform-data:9000"
    MINIO_ACCESS_KEY: str = ""
    MINIO_SECRET_KEY: str = ""
    MINIO_USE_SSL: bool = False
    QDRANT_URL: str = "http://musematic-qdrant.platform-data:6333"
    QDRANT_API_KEY: str = ""
    QDRANT_GRPC_PORT: int = 6334
    QDRANT_COLLECTION_DIMENSIONS: int = 768


settings = Settings()
