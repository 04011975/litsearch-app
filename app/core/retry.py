from __future__ import annotations

import asyncio
import random
from collections.abc import Awaitable, Callable
from typing import TypeVar

T = TypeVar("T")


async def retry_async(
    fn: Callable[[], Awaitable[T]],
    *,
    retries: int = 3,
    base_delay_s: float = 0.5,
    max_delay_s: float = 5.0,
    retry_on: tuple[type[Exception], ...] = (Exception,),
) -> T:
    last_exc: Exception | None = None

    for attempt in range(retries):
        try:
            return await fn()
        except retry_on as exc:
            last_exc = exc

            if attempt >= retries - 1:
                raise

            delay = min(max_delay_s, base_delay_s * (2 ** attempt))
            delay += random.uniform(0, 0.25)
            await asyncio.sleep(delay)

    assert last_exc is not None
    raise last_exc