from typing import Any


class WorkflowExecutionError(Exception):
    def __init__(self, message: str, node: str | None = None, details: Any = None):
        self.node = node
        self.details = details
        super().__init__(message)
