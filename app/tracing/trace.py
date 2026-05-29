from typing import Any


class LocalTraceRecorder:
    def __init__(self):
        self.entries: list[dict[str, Any]] = []

    def record(self, node_name: str, payload: dict[str, Any], status: str, metadata: dict[str, Any] | None = None) -> None:
        entry = {
            "node": node_name,
            "status": status,
            "payload": payload,
            "metadata": metadata or {},
        }
        self.entries.append(entry)

    def as_dict(self) -> dict[str, Any]:
        return {"trace": self.entries}
