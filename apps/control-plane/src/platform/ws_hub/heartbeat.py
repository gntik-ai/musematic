from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import Any


class ConnectionHeartbeat:
    def __init__(self, interval_seconds: int, timeout_seconds: int) -> None:
        self.interval_seconds = interval_seconds
        self.timeout_seconds = timeout_seconds

    async def run(self, conn: Any) -> None:
        while not conn.closed.is_set():
            await asyncio.sleep(self.interval_seconds)
            if conn.closed.is_set():
                return

            now = datetime.now(UTC)
            elapsed = (now - conn.last_pong_at).total_seconds()
            if elapsed > self.timeout_seconds:
                conn.closed.set()
                try:
                    await conn.websocket.close(code=1001, reason="heartbeat-timeout")
                except Exception:
                    pass
                return

            try:
                await conn.websocket.send_bytes(b"")
                conn.last_pong_at = datetime.now(UTC)
            except Exception:
                conn.closed.set()
                return
