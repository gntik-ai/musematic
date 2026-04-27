from __future__ import annotations

THEMES = ("light", "dark", "system", "high_contrast")
LOCALES = ("en", "es", "fr", "de", "ja", "zh-CN")
DEFAULT_LOCALE = "en"
DEFAULT_THEME = "system"
LOCALE_LRU_SIZE = 12
DRIFT_THRESHOLD_DAYS = 7
DATA_EXPORT_FORMATS = ("json", "csv", "ndjson")
KAFKA_TOPIC = "localization.events"

