from __future__ import annotations
from datetime import datetime
from typing import Annotated, Literal, TypedDict
from pydantic import BaseModel, Field

class ExecutionTraceEntry(BaseModel):
    node: str
    status: Literal["success", "failed", "skipped"]
    duration_ms: int
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    details: dict = Field(default_factory=dict)

class PlannerState(BaseModel):
    user_query: str
    intake: dict = Field(default_factory=dict)
    planner: dict = Field(default_factory=dict)
    flights: dict = Field(default_factory=dict)
    hotels: dict = Field(default_factory=dict)
    budget: dict = Field(default_factory=dict)
    visa: dict = Field(default_factory=dict)
    activities: dict = Field(default_factory=dict)
    synthesis: dict = Field(default_factory=dict)
    validation_errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    execution_trace: Annotated[list[ExecutionTraceEntry], "add"] = Field(default_factory=list)
    final_response: str = ""
    status: Literal["pending", "in_progress", "failed", "completed"] = "pending"

    class Config:
        validate_assignment = True
        extra = "forbid"
