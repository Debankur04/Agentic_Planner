import json
import asyncio
from typing import List, Optional
import os

try:
    import aioredis
except Exception as e:
    aioredis = None


class CheckpointStore:
    def __init__(self, redis_url: Optional[str] = None):
        if aioredis is None:
            raise RuntimeError("aioredis is required for CheckpointStore")
        self.redis_url = redis_url or os.environ.get("REDIS_URL", "redis://localhost:6379/0")
        self._redis = None

    async def _ensure(self):
        if self._redis is None:
            self._redis = await aioredis.from_url(self.redis_url, decode_responses=True)

    async def save_state(self, workflow_id: str, state: dict):
        await self._ensure()
        await self._redis.set(f"workflow:{workflow_id}:state", json.dumps(state, default=str))

    async def load_state(self, workflow_id: str) -> Optional[dict]:
        await self._ensure()
        raw = await self._redis.get(f"workflow:{workflow_id}:state")
        if not raw:
            return None
        return json.loads(raw)

    async def append_events(self, workflow_id: str, events: List[dict]):
        if not events:
            return
        await self._ensure()
        payloads = [json.dumps(e, default=str) for e in events]
        await self._redis.rpush(f"workflow:{workflow_id}:events", *payloads)

    async def get_events(self, workflow_id: str, start: int = 0, end: int = -1) -> List[dict]:
        await self._ensure()
        raw = await self._redis.lrange(f"workflow:{workflow_id}:events", start, end)
        return [json.loads(r) for r in raw]

    async def acquire_lock(self, workflow_id: str, lease_seconds: int = 30) -> bool:
        await self._ensure()
        key = f"workflow:{workflow_id}:lock"
        # set if not exists
        ok = await self._redis.set(key, "1", ex=lease_seconds, nx=True)
        return bool(ok)

    async def release_lock(self, workflow_id: str):
        await self._ensure()
        key = f"workflow:{workflow_id}:lock"
        await self._redis.delete(key)
