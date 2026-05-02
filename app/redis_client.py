# app/redis_client.py
from __future__ import annotations

import os
import redis.asyncio as redis  # redis-py >= 4

REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")

def make_redis() -> redis.Redis:
    # decode_responses=True => strings i.p.v. bytes
    return redis.from_url(REDIS_URL, decode_responses=True)