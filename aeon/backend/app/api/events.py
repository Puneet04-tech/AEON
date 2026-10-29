"""Server-sent events: the live event stream and its replay."""
import asyncio
import json
from typing import Optional

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import StreamingResponse

from app.db.client import get_database
from app.security.sessions import Session, require_viewer
from app.services.events import bus, recent, sse_format

router = APIRouter(prefix="/api/v1/events", tags=["events"])

KEEPALIVE_SECONDS = 15


@router.get("/recent")
async def recent_events(since: int = 0, limit: int = 200,
                        session: Session = Depends(require_viewer)):
    return {"events": await recent(get_database(), since_seq=since, limit=min(limit, 500))}


@router.get("/stream")
async def stream(request: Request, token: Optional[str] = Query(default=None),
                 since: int = 0):
    """SSE stream. Authenticate with the Authorization header or ?token=."""
    from app.security.sessions import current_session

    await current_session(request)  # raises 401 when unauthenticated
    db = get_database()

    async def generator():
        queue = await bus.subscribe()
        try:
            backlog = await recent(db, since_seq=since, limit=200)
            for event in backlog:
                yield sse_format(event)
            yield ": connected\n\n"
            while True:
                if await request.is_disconnected():
                    break
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=KEEPALIVE_SECONDS)
                    yield sse_format(event)
                except asyncio.TimeoutError:
                    yield ": keepalive\n\n"
        except asyncio.CancelledError:  # client went away
            raise
        finally:
            await bus.unsubscribe(queue)

    return StreamingResponse(generator(), media_type="text/event-stream", headers={
        "Cache-Control": "no-cache, no-transform",
        "X-Accel-Buffering": "no",
        "Connection": "keep-alive",
    })
