import json
import os
from typing import List, Optional

try:
    import aioredis
except Exception:
    aioredis = None


class TracePersist:
    def __init__(self, redis_url: Optional[str] = None):
        if aioredis is None:
            raise RuntimeError("aioredis is required for TracePersist")
        self.redis_url = redis_url or os.environ.get("REDIS_URL", "redis://localhost:6379/0")
        self._redis = None

    async def _ensure(self):
        if self._redis is None:
            self._redis = await aioredis.from_url(self.redis_url, decode_responses=True)

    async def persist_trace_events(self, workflow_id: str, events: List[dict]):
        if not events:
            return
        await self._ensure()
        payloads = [json.dumps(e, default=str) for e in events]
        await self._redis.rpush(f"workflow:{workflow_id}:traces", *payloads)

    async def fetch_traces(self, workflow_id: str, start: int = 0, end: int = -1) -> List[dict]:
        await self._ensure()
        raw = await self._redis.lrange(f"workflow:{workflow_id}:traces", start, end)
        return [json.loads(r) for r in raw]
