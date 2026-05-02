# app/services/redis_policy.py
from __future__ import annotations

import hashlib
import json
import time
import uuid
from typing import Any, Optional


def make_cache_key(prefix: str, payload: dict[str, Any]) -> str:
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    return f"{prefix}:{digest}"


async def cache_get_json(redis, key: str) -> Optional[dict]:
    if redis is None:
        return None

    try:
        val = await redis.get(key)
    except Exception:
        return None

    if not val:
        return None

    try:
        if isinstance(val, bytes):
            val = val.decode("utf-8", errors="replace")
        return json.loads(val)
    except Exception:
        return None


async def cache_set_json(redis, key: str, obj: Any, ttl_s: int) -> bool:
    if redis is None:
        return False

    try:
        await redis.set(key, json.dumps(obj), ex=int(ttl_s))
        return True
    except Exception:
        return False


async def rate_limit_sliding_window(redis, key: str, limit: int, window_s: int) -> bool:
    """
    Sliding window limiter using ZSET.
    Returns True if allowed, False if rate-limited.

    If redis is None or unavailable, rate limiting is skipped and the request is allowed.
    """
    if redis is None:
        return True

    try:
        now_ms = int(time.time() * 1000)
        window_ms = int(window_s) * 1000
        member = f"{now_ms}-{uuid.uuid4().hex}"

        pipe = redis.pipeline()
        pipe.zremrangebyscore(key, 0, now_ms - window_ms)
        pipe.zadd(key, {member: now_ms})
        pipe.zcard(key)
        pipe.expire(key, int(window_s) + 2)
        _, _, count, _ = await pipe.execute()

        return int(count) <= int(limit)
    except Exception:
        return True