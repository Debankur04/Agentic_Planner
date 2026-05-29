from pydantic import BaseModel
from typing import Any

class NodeResult(BaseModel):
    success: bool
    payload: dict
    errors: list[str] = []
    warnings: list[str] = []

class WorkflowResult(BaseModel):
    status: str
    state: dict
    message: str | None = None
