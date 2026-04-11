from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from platform.ws_hub.schemas import EventsDroppedMessage
from typing import Any


class ConnectionWriter:
    async def run(self, conn: Any) -> None:
        while True:
            if conn.closed.is_set() and conn.send_queue.empty():
                return

            try:
                message = await asyncio.wait_for(conn.send_queue.get(), timeout=0.1)
            except TimeoutError:
                continue

            try:
                if conn.dropped_count > 0:
                    dropped = EventsDroppedMessage(
                        channel=None,
                        count=conn.dropped_count,
                        dropped_at=datetime.now(UTC),
                    )
                    conn.dropped_count = 0
                    await conn.websocket.send_text(dropped.model_dump_json())

                payload = (
                    message.model_dump_json()
                    if hasattr(message, "model_dump_json")
                    else str(message)
                )
                await conn.websocket.send_text(payload)
            except Exception:
                conn.closed.set()
                return

