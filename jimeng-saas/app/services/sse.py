"""Per-user SSE event bus. In-process asyncio queues for dev.

For prod multi-worker, swap publish() to Redis pub/sub and Subscriber to subscribe.
The HTTP handler (_stream) stays the same.
"""
from __future__ import annotations

import asyncio
import json
from collections import defaultdict
from typing import Any

# user_id → list of asyncio.Queue
_subscribers: dict[int, list[asyncio.Queue]] = defaultdict(list)
_lock = asyncio.Lock()


async def subscribe(user_id: int) -> asyncio.Queue:
    q: asyncio.Queue = asyncio.Queue(maxsize=100)
    async with _lock:
        _subscribers[user_id].append(q)
    return q


async def unsubscribe(user_id: int, q: asyncio.Queue) -> None:
    async with _lock:
        if q in _subscribers[user_id]:
            _subscribers[user_id].remove(q)
            if not _subscribers[user_id]:
                _subscribers.pop(user_id, None)


async def publish(user_id: int, event: str, data: Any) -> None:
    """Fire-and-forget. Drops if a subscriber's queue is full."""
    payload = json.dumps({"event": event, "data": data}, default=str, ensure_ascii=False)
    async with _lock:
        subs = list(_subscribers.get(user_id, []))
    for q in subs:
        try:
            q.put_nowait(payload)
        except asyncio.QueueFull:
            # Drop oldest then retry so the latest event wins.
            try:
                q.get_nowait()
                q.put_nowait(payload)
            except Exception:
                pass


def publish_sync(user_id: int, event: str, data: Any) -> None:
    """Sync entry for use from RQ worker. Schedules publish on the running loop if any,
    else on a fresh one."""
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            asyncio.run_coroutine_threadsafe(publish(user_id, event, data), loop)
        else:
            loop.run_until_complete(publish(user_id, event, data))
    except RuntimeError:
        # No running loop in this thread (typical in RQ worker) — make one.
        try:
            asyncio.run(publish(user_id, event, data))
        except Exception:
            pass  # SSE is best-effort; never fail the job because the user is offline
