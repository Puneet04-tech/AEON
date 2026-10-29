"""In-process event bus backing the SSE stream.

Events are persisted (so a reconnecting dashboard can replay) and fanned out to
subscribers. Single process only, which matches the deployment.
"""
import asyncio
import json
import uuid
from datetime import datetime, timezone
from typing import Dict, List, Optional, Set

import structlog

logger = structlog.get_logger()


class EventBus:
    def __init__(self) -> None:
        self._subscribers: Set[asyncio.Queue] = set()
        self._lock = asyncio.Lock()

    async def subscribe(self) -> asyncio.Queue:
        queue: asyncio.Queue = asyncio.Queue(maxsize=500)
        async with self._lock:
            self._subscribers.add(queue)
        return queue

    async def unsubscribe(self, queue: asyncio.Queue) -> None:
        async with self._lock:
            self._subscribers.discard(queue)

    async def publish(self, event: dict) -> None:
        dead: List[asyncio.Queue] = []
        for queue in list(self._subscribers):
            try:
                queue.put_nowait(event)
            except asyncio.QueueFull:
                dead.append(queue)
        for queue in dead:
            await self.unsubscribe(queue)

    def subscriber_count(self) -> int:
        return len(self._subscribers)

    def reset(self) -> None:
        self._subscribers.clear()


bus = EventBus()


async def emit(db, event_type: str, payload: dict, trade_id: Optional[str] = None,
               actor: str = "system", persist: bool = True) -> dict:
    counter = await db.kv.find_one_and_update(
        {"key": "event_seq"}, {"$inc": {"value": 1}}, upsert=True,
        return_document=True,
    )
    seq = int(counter["value"]) if counter and isinstance(counter.get("value"), int) else 1
    event = {
        "id": f"evt_{uuid.uuid4().hex[:16]}",
        "seq": seq,
        "type": event_type,
        "trade_id": trade_id,
        "actor": actor,
        "payload": payload,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    if persist:
        await db.events.insert_one({**event})
    await bus.publish(event)
    return event


async def recent(db, since_seq: int = 0, limit: int = 200) -> List[dict]:
    cursor = db.events.find({"seq": {"$gt": since_seq}}, {"_id": 0}).sort("seq", 1).limit(limit)
    return [doc async for doc in cursor]


def sse_format(event: dict) -> str:
    return f"id: {event['seq']}\nevent: {event['type']}\ndata: {json.dumps(event)}\n\n"
