from __future__ import annotations

from collections.abc import Iterator, MutableMapping

try:
    from opentelemetry import propagate
    from opentelemetry.context import Context
except ImportError:  # pragma: no cover - fallback for minimal local test environments

    class Context:  # type: ignore[no-redef]
        pass

    def _inject(*, carrier: object) -> None:
        return None

    def _extract(*, carrier: object) -> Context:
        return Context()
else:
    def _inject(*, carrier: object) -> None:
        propagate.inject(carrier=carrier)

    def _extract(*, carrier: object) -> Context:
        return propagate.extract(carrier=carrier)


class _BytesDictCarrier(MutableMapping[str, str]):
    def __init__(self, headers: dict[str, bytes]) -> None:
        self._headers = headers

    def __getitem__(self, key: str) -> str:
        value = self._headers[key]
        return value.decode("utf-8")

    def __setitem__(self, key: str, value: str) -> None:
        self._headers[key] = value.encode("utf-8")

    def __delitem__(self, key: str) -> None:
        del self._headers[key]

    def __iter__(self) -> Iterator[str]:
        return iter(self._headers)

    def __len__(self) -> int:
        return len(self._headers)


def inject_trace_context(headers: dict[str, bytes]) -> dict[str, bytes]:
    carrier = _BytesDictCarrier(headers)
    _inject(carrier=carrier)
    return headers


def extract_trace_context(headers: dict[str, bytes]) -> Context:
    carrier = _BytesDictCarrier(headers)
    return _extract(carrier=carrier)
