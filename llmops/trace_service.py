import time, json
from dataclasses import dataclass, field
from typing import Any, List
from uuid import uuid4
from backend.mongo import save_trace


@dataclass
class TraceEvent:
    step: int
    event_type: str
    data: Any
    timestamp_ms: float= field(default_factory= lambda: time.time() * 1000)
    latency_ms: float = 0.0

class ExecutionTrace:
    def __init__(self, request_id: str = None):
        self.request_id = request_id or str(uuid4())
        self.events: List[TraceEvent] = []
        self._step = 0
        self._start = time.time() * 1000

    def record(self, event_type: str, data: Any, latency_ms: float = 0.0):
        self._step += 1
        self.events.append(TraceEvent(
            step=self._step,
            event_type=event_type,
            data=data,
            latency_ms=latency_ms
        ))
    

    def to_dict(self) -> dict:
        total_ms = (time.time() * 1000) - self._start

        def _safe_serialize(data):
            try:
                return json.dumps(data)
            except:
                return str(data)
        return {
            "request_id": self.request_id,
            "total_latency_ms": total_ms,
            "step_count": self._step,
            "events": [
                {"step": e.step, "type": e.event_type,
                 "latency_ms": e.latency_ms, "data": _safe_serialize(e.data)[:500]}
                for e in self.events
            ]
        }

    def save_to_redis(self, redis_client, ttl: int = 86400):
        redis_client.setex(
            f"trace:{self.request_id}",
            ttl,
            json.dumps(self.to_dict())
        )
    
    def save_to_db(self):
        save_trace(self.to_dict())

        