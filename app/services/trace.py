from __future__ import annotations
from datetime import datetime
from typing import Any


class TraceCollector:
    def __init__(self):
        self.entries: list[dict[str, Any]] = []
        self.started_at: datetime | None = None
        self.user_query: str | None = None

    def start_workflow(self, user_query: str) -> None:
        self.started_at = datetime.utcnow()
        self.user_query = user_query
        self.entries.clear()

    def append(self, node_name: str, status: str, duration_ms: int, details: dict[str, Any] | None = None) -> None:
        self.entries.append(
            {
                "node": node_name,
                "status": status,
                "duration_ms": duration_ms,
                "timestamp": datetime.utcnow().isoformat() + "Z",
                "details": details or {},
            }
        )

    def summary(self) -> dict[str, Any]:
        return {
            "user_query": self.user_query,
            "started_at": self.started_at.isoformat() + "Z" if self.started_at else None,
            "entries": self.entries,
        }


class StreamEvent:
    def __init__(self, event_type: str, payload: dict[str, Any]):
        self.type = event_type
        self.payload = payload

    def dict(self) -> dict[str, Any]:
        return {"type": self.type, "payload": self.payload}
