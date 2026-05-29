from __future__ import annotations
from datetime import datetime
from typing import Any, Dict, List, Literal, Optional
import logging

from pydantic import BaseModel, Field, field_validator, model_validator

from agent_file.utils.serialization import safe_jsonable_encoder


logger = logging.getLogger(__name__)

class IntakeValidationState(BaseModel):
    status: Literal["pending", "completed", "failed", "needs_clarification"] = "pending"
    validation_results: Dict[str, Any] = Field(default_factory=dict)
    initial_plan: Dict[str, Any] = Field(default_factory=dict)
    user_clarifications_needed: List[str] = Field(default_factory=list)
    missing_information: List[str] = Field(default_factory=list)
    confidence: int = Field(0, ge=0, le=100)

    # @model_validator(mode="after")
    # def ensure_plan_structure(cls, model):
    #     logger.debug("IntakeValidationState.ensure_plan_structure: status=%s initial_plan=%s", model.status, model.initial_plan)
    #     if model.status == "validated" and not model.initial_plan.get("estimated_steps"):
    #         return model.model_copy(update={
    #             "initial_plan": {
    #                 "phase": "planning",
    #                 "estimated_steps": [
    #                     "Interpret the original user query and propose an initial phase plan"
    #                 ],
    #                 "key_decisions": {},
    #                 "source": "fallback"
    #             },
    #             "missing_information": model.missing_information + ["initial_plan.estimated_steps"],
    #             "confidence": max(model.confidence, 20)
    #         })
    #     return model


class ResearchPricingState(BaseModel):
    status: Literal["pending", "completed", "failed"] = "pending"
    plan_from_intake: Dict[str, Any] = Field(default_factory=dict)
    research_results: Dict[str, Any] = Field(default_factory=dict)
    pricing_data: Dict[str, Any] = Field(default_factory=dict)
    recommendations: List[str] = Field(default_factory=list)
    issues_found: List[Dict[str, Any]] = Field(default_factory=list)
    tool_usage_log: List[Dict[str, Any]] = Field(default_factory=list)

    # @model_validator(mode="after")
    # def preserve_plan_received(cls, model):
    #     logger.debug("ResearchPricingState.preserve_plan_received: plan_from_intake=%s", model.plan_from_intake)
    #     if not model.plan_from_intake:
    #         return model.model_copy(update({"plan_from_intake": {"estimated_steps": [], "source": "missing"}}))
    #     return model


class WritingState(BaseModel):
    status: Literal["pending", "completed", "failed"] = "pending"
    research_data: Dict[str, Any] = Field(default_factory=dict)
    final_output: str = ""
    formatting_applied: List[str] = Field(default_factory=list)
    output_metadata: Dict[str, Any] = Field(default_factory=dict)
    cleanup: Dict[str, Any] = Field(default_factory=dict)

    @field_validator("final_output", mode="before")
    def validate_final_output(cls, value):
        if value is None:
            return ""
        return str(value)


class WorkflowState(BaseModel):
    workflow_id: str
    created_at: str
    user_query: str
    metadata: Dict[str, Any] = Field(default_factory=dict)
    intake_validation: IntakeValidationState = Field(default_factory=IntakeValidationState)
    research_pricing: ResearchPricingState = Field(default_factory=ResearchPricingState)
    writing: WritingState = Field(default_factory=WritingState)
    final_response: str = ""
    global_trace: List[Dict[str, Any]] = Field(default_factory=list)
    status: Literal["pending", "running", "completed", "failed"] = "pending"
    completeness_score: int = Field(0, ge=0, le=100)
    warnings: List[str] = Field(default_factory=list)

    class Config:
        validate_assignment = True
        extra = "forbid"

    @model_validator(mode="before")
    def require_user_query(cls, values):
        if not values.get("user_query"):
            raise ValueError("user_query is required for WorkflowState")
        return values

    def snapshot(self, redact_keys: Optional[List[str]] = None) -> Dict[str, Any]:
        data = self.model_dump()
        if redact_keys:
            for key in redact_keys:
                if key in data:
                    data[key] = "REDACTED"
        return safe_jsonable_encoder(data)

    def calculate_completeness(self) -> int:
        score = 0
        score += 30 if self.intake_validation.status == "completed" else 0
        score += 30 if self.research_pricing.status == "completed" else 0
        score += 30 if self.writing.status == "completed" else 0
        score += 10 if bool(self.final_response and self.final_response.strip()) else 0
        self.completeness_score = min(100, score)
        return self.completeness_score


class ValidationResult(BaseModel):
    status: Literal["validated", "needs_clarification", "invalid"] = "validated"
    confidence: int = Field(0, ge=0, le=100)
    extracted_requirements: Dict[str, Any] = Field(default_factory=dict)
    missing_information: List[str] = Field(default_factory=list)
    concerns: List[str] = Field(default_factory=list)
    initial_plan: Dict[str, Any] = Field(default_factory=dict)
    clarification_questions: List[str] = Field(default_factory=list)
    reasoning: str = ""
    trace_markers: Dict[str, Any] = Field(default_factory=dict)

    # @model_validator(mode="after")
    # def enforce_initial_plan(cls, model):
    #     logger.debug("ValidationResult.enforce_initial_plan: status=%s initial_plan=%s", model.status, model.initial_plan)
    #     if model.status == "validated" and not model.initial_plan.get("estimated_steps"):
    #         return model.model_copy(update={
    #             "initial_plan": {
    #                 "phase": "planning",
    #                 "estimated_steps": [
    #                     "Interpret the user query and create an initial plan based on extracted requirements"
    #                 ],
    #                 "key_decisions": {},
    #                 "source": "fallback"
    #             },
    #             "missing_information": model.missing_information + ["initial_plan.estimated_steps"],
    #             "concerns": model.concerns + ["Fallback initial plan created because intake extraction did not include steps."],
    #             "confidence": max(model.confidence, 20)
    #         })
    #     return model


class ResearchResult(BaseModel):
    status: Literal["research_complete", "partial_results", "research_failed"] = "research_complete"
    plan_received: Dict[str, Any] = Field(default_factory=dict)
    research_results: Dict[str, Any] = Field(default_factory=dict)
    pricing_summary: Dict[str, Any] = Field(default_factory=dict)
    issues_identified: List[Dict[str, Any]] = Field(default_factory=list)
    recommendations: List[str] = Field(default_factory=list)
    data_gaps: List[str] = Field(default_factory=list)
    tool_usage_log: List[Dict[str, Any]] = Field(default_factory=list)
    reasoning: str = ""
    trace_markers: Dict[str, Any] = Field(default_factory=dict)

    # @model_validator(mode="after")
    # def ensure_plan_received(cls, model):
    #     logger.debug("ResearchResult.ensure_plan_received: plan_received=%s", model.plan_received)
    #     if not model.plan_received:
    #         return model.model_copy(update={"plan_received": {"estimated_steps": [], "source": "missing"}})
    #     return model


class WriterResult(BaseModel):
    status: Literal["writing_complete", "writing_failed"] = "writing_complete"
    final_output: str
    output_structure: List[str] = Field(default_factory=list)
    formatting_applied: List[str] = Field(default_factory=list)
    character_count: int = Field(0, ge=0)
    estimated_read_time: str = ""
    included_sections: Dict[str, bool] = Field(default_factory=dict)
    quality_checks: Dict[str, Any] = Field(default_factory=dict)
    cleanup_log: Dict[str, Any] = Field(default_factory=dict)
    reasoning: str = ""
    trace_markers: Dict[str, Any] = Field(default_factory=dict)

    @field_validator("final_output", mode="before")
    def validate_final_output(cls, value):
        value = str(value or "").strip()
        if not value:
            raise ValueError("final_output is required and cannot be empty")
        if "user's request is not provided" in value.lower():
            raise ValueError("final_output indicates missing original user input")
        return value


def create_workflow_state(
    user_query: str,
    workflow_id: str,
    request_id: str,
    conversation_id: str,
    user_id: str,
) -> WorkflowState:
    created_at = datetime.utcnow().isoformat()
    return WorkflowState(
        workflow_id=workflow_id,
        created_at=created_at,
        user_query=user_query,
        metadata={
            "request_id": request_id,
            "conversation_id": conversation_id,
            "user_id": user_id,
            "created_at": created_at,
            "updated_at": created_at,
        },
        status="running"
    )


def calculate_state_completeness(state: WorkflowState) -> int:
    return state.calculate_completeness()
