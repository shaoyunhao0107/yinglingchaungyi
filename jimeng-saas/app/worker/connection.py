"""RQ connection + queue. Singleton per process."""
from __future__ import annotations

import os

from redis import Redis
from rq import Queue

_redis: Redis | None = None
_queue: Queue | None = None


def get_redis() -> Redis:
    global _redis
    if _redis is None:
        _redis = Redis.from_url(os.environ.get("JSA_REDIS_URL", "redis://localhost:6379/0"))
    return _redis


def get_queue() -> Queue:
    global _queue
    if _queue is None:
        _queue = Queue("jimeng", connection=get_redis())
    return _queue
