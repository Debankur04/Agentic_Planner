"""
Multi-Agent Implementations
Implements Intake Validator, Research & Pricing, and Writer agents
"""

from langchain_core.messages import SystemMessage, HumanMessage, AIMessage
from langchain_core.tools import tool
import json
import time
from typing import Dict, Any, List, Optional
from datetime import datetime
import logging

from pydantic import ValidationError

from agent_file.utils.communication_manager import CommunicationManager, TraceRecorder
from agent_file.prompt_library.multi_agent_prompts import (
    INTAKE_VALIDATION_SYSTEM_PROMPT,
    INTAKE_VALIDATION_USER_PROMPT_TEMPLATE,
    RESEARCH_PRICING_SYSTEM_PROMPT,
    RESEARCH_PRICING_USER_PROMPT_TEMPLATE,
    WRITING_SYSTEM_PROMPT,
    WRITING_USER_PROMPT_TEMPLATE
)
from agent_file.schemas import ValidationResult, ResearchResult, WriterResult
from agent_file.agent.exceptions import MissingStateError

logger = logging.getLogger(__name__)


class IntakeValidatorAgent:
    """
    Phase 1: Intake Validator Agent
    Validates input, identifies missing information, creates initial plan
    """
    
    def __init__(self, llm, comm_manager: CommunicationManager, 
                 trace_recorder: TraceRecorder, tools: List[tool] = None):
        self.llm = llm
        self.comm_manager = comm_manager
        self.trace_recorder = trace_recorder
        self.tools = tools or []
        self.agent_name = "intake_validator"
    
    def validate_input(self, user_input: str, context: Dict[str, Any] = None,
                      custom_prompt: str = None) -> Dict[str, Any]:
        """
        Validate user input and create initial plan
        
        Args:
            user_input: Raw user input to validate
            context: Additional context (user_id, preferences, etc.)
            custom_prompt: Optional custom system prompt for this phase
        
        Returns:
            Validation results with initial plan
        """
        context = context or {}
        start_time = time.time()
        print(context)
        
        self.trace_recorder.record_event(
            phase="intake_validation",
            agent=self.agent_name,
            event_type="validation_started",
            data={"input_length": len(user_input)}
        )
        
        try:
            # Prepare the validation prompt
            system_prompt = custom_prompt or INTAKE_VALIDATION_SYSTEM_PROMPT
            
            # Build user prompt with context
            user_prompt = INTAKE_VALIDATION_USER_PROMPT_TEMPLATE.format(
                domain=context.get("domain", "general"),
                user_input=user_input,
                user_id=context.get("user_id", "unknown"),
                has_history="yes" if context.get("history") else "no",
                preferences=str(context.get("preferences", {}))[:200]
            )
            
            # Create messages
            messages = [
                SystemMessage(content=system_prompt),
                HumanMessage(content=user_prompt)
            ]
            
            # Call LLM
            self.trace_recorder.record_event(
                phase="intake_validation",
                agent=self.agent_name,
                event_type="llm_invoked",
                data={"message_count": len(messages)}
            )
            
            llm_start = time.time()
            response = self.llm.invoke(messages)
            llm_duration = (time.time() - llm_start) * 1000
            
            self.trace_recorder.record_event(
                phase="intake_validation",
                agent=self.agent_name,
                event_type="llm_response_received",
                metadata={"duration_ms": llm_duration}
            )
            
            # Parse response
            response_text = response.content
            
            # Try to extract JSON from response and validate against the typed schema.
            raw_validation = self._parse_validation_response(response_text)
            try:
                validation = ValidationResult.model_validate(raw_validation)
            except ValidationError as exc:
                logger.warning("Intake validation output failed schema validation; applying safe fallback.", exc_info=True)
                self.trace_recorder.record_error(
                    phase="intake_validation",
                    agent=self.agent_name,
                    error="validation_schema_error",
                    error_details=str(exc)
                )
                validation = ValidationResult(
                    status="needs_clarification",
                    confidence=0,
                    extracted_requirements={},
                    missing_information=["structured_intake_plan"],
                    concerns=["Unable to parse intake response into valid JSON schema."],
                    clarification_questions=[
                        "Please clarify your request with destination, dates, budget, and travel style so I can create a safe plan."
                    ],
                    reasoning="Fallback due to invalid intake validation schema."
                )

            if validation.status == "validated" and not validation.initial_plan.get("estimated_steps"):
                self.trace_recorder.record_event(
                    phase="intake_validation",
                    agent=self.agent_name,
                    event_type="fallback_plan_created",
                    data={
                        "reason": "missing_estimated_steps",
                        "original_user_input": user_input[:200]
                    }
                )
                validation.initial_plan = {
                    "phase": "planning",
                    "estimated_steps": [
                        "Interpret the user's request and create an initial plan from the provided input."
                    ],
                    "key_decisions": {},
                    "source": "fallback"
                }
                validation.missing_information.append("initial_plan.estimated_steps")
                validation.concerns.append("Fallback initial plan created because extracted plan was missing steps.")
                validation.confidence = max(validation.confidence, 20)

            validation_result = validation.model_dump()

            # Save to communication file
            self.comm_manager.save_agent_output(
                "intake_validation",
                "validation_results",
                validation_result
            )
            
            # Record decision
            self.trace_recorder.record_decision(
                phase="intake_validation",
                agent=self.agent_name,
                decision=validation_result.get("status", "unknown"),
                reasoning=validation_result.get("reasoning", ""),
                alternatives=["needs_clarification", "invalid", "validated"]
            )
            
            # Check if clarification is needed
            if validation_result.get("status") == "needs_clarification":
                self.trace_recorder.record_event(
                    phase="intake_validation",
                    agent=self.agent_name,
                    event_type="clarification_needed",
                    data={
                        "questions_count": len(validation_result.get("clarification_questions", [])),
                        "questions": validation_result.get("clarification_questions", [])[:3]
                    }
                )
            
            # Update communication file status
            self.comm_manager.update_phase(
                "intake_validation",
                "completed",
                {
                    "validation_results": validation_result,
                    "initial_plan": validation_result.get("initial_plan", {}),
                    "user_clarifications_needed": validation_result.get("clarification_questions", [])
                }
            )
            
            total_duration = (time.time() - start_time) * 1000
            
            self.trace_recorder.record_event(
                phase="intake_validation",
                agent=self.agent_name,
                event_type="validation_completed",
                metadata={"total_duration_ms": total_duration}
            )
            
            return {
                "status": "success",
                "validation": validation_result,
                "duration_ms": total_duration
            }
            
        except Exception as e:
            logger.error(f"Error in intake validation: {e}")
            self.trace_recorder.record_error(
                phase="intake_validation",
                agent=self.agent_name,
                error=str(e),
                error_details=str(e.__traceback__)
            )
            
            return {
                "status": "error",
                "error": str(e),
                "duration_ms": (time.time() - start_time) * 1000
            }
    
    def _parse_validation_response(self, response_text: str) -> Dict[str, Any]:
        """Parse JSON from LLM response"""
        try:
            # Try direct JSON parsing
            return json.loads(response_text)
        except json.JSONDecodeError:
            # Try to extract JSON from response
            import re
            json_match = re.search(r'\{.*\}', response_text, re.DOTALL)
            if json_match:
                try:
                    return json.loads(json_match.group())
                except json.JSONDecodeError:
                    pass
            
            # Fallback to structured response
            return {
                "status": "validated",
                "confidence": 60,
                "extracted_requirements": {"raw_input": response_text},
                "missing_information": [],
                "concerns": [],
                "initial_plan": {"raw_response": response_text},
                "clarification_questions": [],
                "reasoning": "Parsed from LLM response"
            }


class ResearchPricingAgent:
    """
    Phase 2: Research & Pricing Agent
    Conducts research, gathers pricing, identifies issues
    """
    
    def __init__(self, llm, comm_manager: CommunicationManager,
                 trace_recorder: TraceRecorder, tools: List[tool] = None):
        self.llm = llm
        self.comm_manager = comm_manager
        self.trace_recorder = trace_recorder
        self.tools = tools or []
        self.tool_map = {tool.name: tool for tool in tools} if tools else {}
        self.agent_name = "research_pricing"
    
    def conduct_research(self, initial_plan: Dict[str, Any], 
                        context: Dict[str, Any] = None,
                        custom_prompt: str = None,
                        max_api_calls: int = 10) -> Dict[str, Any]:
        """
        Conduct research based on initial plan
        
        Args:
            initial_plan: Plan from intake validator
            context: Additional context
            custom_prompt: Optional custom system prompt
            max_api_calls: Maximum API calls allowed
        
        Returns:
            Research results with pricing and recommendations
        """
        context = context or {}
        start_time = time.time()
        api_calls_made = 0
        
        self.trace_recorder.record_event(
            phase="research_pricing",
            agent=self.agent_name,
            event_type="research_started",
            data={
                "plan_received": True,
                "max_api_calls": max_api_calls
            }
        )
        
        try:
            user_input = context.get("user_input")
            if not user_input:
                raise MissingStateError(["user_input"], state=context)

            if not initial_plan or not initial_plan.get("estimated_steps"):
                raise MissingStateError(["initial_plan.estimated_steps"], state=initial_plan)

            # Prepare research prompt
            system_prompt = custom_prompt or RESEARCH_PRICING_SYSTEM_PROMPT
            
            # Build focus areas from plan
            focus_areas = initial_plan.get("estimated_steps", [])
            tools_list = [t.name for t in self.tools][:5]  # Limit list
            
            user_prompt = RESEARCH_PRICING_USER_PROMPT_TEMPLATE.format(
                user_input=user_input,
                initial_plan=json.dumps(initial_plan, indent=2)[:500],
                validated_requirements=str(context.get("requirements", {}))[:300],
                research_focus_areas="\n".join(focus_areas) if focus_areas else "general research",
                tools_list=", ".join(tools_list),
                max_api_calls=max_api_calls,
                timeout_seconds=60,
                data_freshness_days=7
            )
            
            messages = [
                SystemMessage(content=system_prompt),
                HumanMessage(content=user_prompt)
            ]
            
            self.trace_recorder.record_event(
                phase="research_pricing",
                agent=self.agent_name,
                event_type="llm_invoked",
                data={"message_count": len(messages)}
            )
            
            llm_start = time.time()
            response = self.llm.invoke(messages)
            llm_duration = (time.time() - llm_start) * 1000
            
            # Parse response
            response_text = response.content
            raw_research_result = self._parse_research_response(response_text)
            try:
                research_result = ResearchResult.model_validate(raw_research_result)
            except ValidationError as exc:
                logger.warning("Research pricing output failed schema validation; applying safe fallback.", exc_info=True)
                self.trace_recorder.record_error(
                    phase="research_pricing",
                    agent=self.agent_name,
                    error="research_schema_error",
                    error_details=str(exc)
                )
                research_result = ResearchResult(
                    status="research_complete",
                    plan_received=initial_plan,
                    research_results={"raw_findings": response_text},
                    pricing_summary={},
                    issues_identified=[],
                    recommendations=[],
                    data_gaps=["unable_to_parse_structured_research"],
                    tool_usage_log=[],
                    reasoning="Fallback research result created because response did not match the expected schema."
                )

            # Record tool usage
            tool_log = research_result.tool_usage_log
            for tool_usage in tool_log:
                api_calls_made += tool_usage.get("calls_made", 0)
                self.trace_recorder.record_event(
                    phase="research_pricing",
                    agent=self.agent_name,
                    event_type="tool_usage",
                    data=tool_usage
                )
            
            # Record issues found
            issues = research_result.issues_identified
            if issues:
                self.trace_recorder.record_event(
                    phase="research_pricing",
                    agent=self.agent_name,
                    event_type="issues_identified",
                    data={"count": len(issues), "issues": issues[:3]}
                )
            
            # Save research results
            self.comm_manager.save_agent_output(
                "research_pricing",
                "research_results",
                research_result.research_results
            )
            
            self.comm_manager.save_agent_output(
                "research_pricing",
                "pricing_data",
                research_result.pricing_summary
            )
            
            self.comm_manager.update_phase(
                "research_pricing",
                "completed",
                {
                    "plan_from_intake": initial_plan,
                    "research_results": research_result.research_results,
                    "pricing_data": research_result.pricing_summary,
                    "recommendations": research_result.recommendations,
                    "issues_found": issues
                }
            )
            
            total_duration = (time.time() - start_time) * 1000
            
            self.trace_recorder.record_event(
                phase="research_pricing",
                agent=self.agent_name,
                event_type="research_completed",
                data={
                    "api_calls_made": api_calls_made,
                    "issues_found": len(issues),
                    "recommendations_count": len(research_result.recommendations)
                },
                metadata={"total_duration_ms": total_duration}
            )
            
            return {
                "status": "success",
                "research": research_result.model_dump(),
                "api_calls_made": api_calls_made,
                "duration_ms": total_duration
            }
            
        except Exception as e:
            logger.error(f"Error in research: {e}")
            self.trace_recorder.record_error(
                phase="research_pricing",
                agent=self.agent_name,
                error=str(e)
            )
            
            return {
                "status": "error",
                "error": str(e),
                "duration_ms": (time.time() - start_time) * 1000
            }
    
    def _parse_research_response(self, response_text: str) -> Dict[str, Any]:
        """Parse JSON from LLM response"""
        try:
            return json.loads(response_text)
        except json.JSONDecodeError:
            import re
            json_match = re.search(r'\{.*\}', response_text, re.DOTALL)
            if json_match:
                try:
                    return json.loads(json_match.group())
                except json.JSONDecodeError:
                    pass
            
            return {
                "status": "research_complete",
                "research_results": {"raw_findings": response_text},
                "pricing_summary": {},
                "issues_identified": [],
                "recommendations": [],
                "tool_usage_log": []
            }


class WriterAgent:
    """
    Phase 3: Writer Agent
    Synthesizes research into beautiful user output and cleans up
    """
    
    def __init__(self, llm, comm_manager: CommunicationManager,
                 trace_recorder: TraceRecorder):
        self.llm = llm
        self.comm_manager = comm_manager
        self.trace_recorder = trace_recorder
        self.agent_name = "writer"
    
    def write_final_output(self, research_data: Dict[str, Any],
                          context: Dict[str, Any] = None,
                          custom_prompt: str = None) -> Dict[str, Any]:
        """
        Write final user-facing output
        
        Args:
            research_data: Compiled research and pricing data
            context: Additional context (tone, audience, etc.)
            custom_prompt: Optional custom system prompt
        
        Returns:
            Final output with formatting and cleanup log
        """
        context = context or {}
        start_time = time.time()
        
        self.trace_recorder.record_event(
            phase="writing",
            agent=self.agent_name,
            event_type="writing_started",
            data={"research_data_size": len(str(research_data))}
        )
        
        user_input = context.get("user_input")
        if not user_input:
            raise MissingStateError(["user_input"], state=context)

        if not research_data or not research_data.get("research_results"):
            raise MissingStateError(["research_data.research_results"], state=research_data)

        try:
            # Prepare writing prompt
            system_prompt = custom_prompt or WRITING_SYSTEM_PROMPT
            
            user_prompt = WRITING_USER_PROMPT_TEMPLATE.format(
                user_input=user_input,
                research_summary=json.dumps(research_data, indent=2)[:1000],
                pricing_options=json.dumps(research_data.get("pricing_data", {}), indent=2)[:500],
                recommendations="\n".join(research_data.get("recommendations", []))[:300],
                issues=json.dumps(research_data.get("issues_found", []))[:300],
                output_format=context.get("output_format", "markdown"),
                target_audience=context.get("audience", "general user"),
                tone=context.get("tone", "professional"),
                include_pricing=str(context.get("include_pricing", True)),
                include_disclaimers=str(context.get("include_disclaimers", True))
            )
            
            messages = [
                SystemMessage(content=system_prompt),
                HumanMessage(content=user_prompt)
            ]
            
            self.trace_recorder.record_event(
                phase="writing",
                agent=self.agent_name,
                event_type="llm_invoked",
                data={"message_count": len(messages)}
            )
            
            llm_start = time.time()
            response = self.llm.invoke(messages)
            llm_duration = (time.time() - llm_start) * 1000
            
            # Parse response
            response_text = response.content
            raw_writing_result = self._parse_writing_response(response_text)
            try:
                writing_result = WriterResult.model_validate(raw_writing_result)
            except ValidationError as exc:
                logger.warning("Writer output failed schema validation; applying safe fallback.", exc_info=True)
                self.trace_recorder.record_error(
                    phase="writing",
                    agent=self.agent_name,
                    error="writer_schema_error",
                    error_details=str(exc)
                )
                writing_result = WriterResult(
                    status="writing_complete",
                    final_output=response_text,
                    output_structure=["final_output"],
                    formatting_applied=["fallback_text"],
                    character_count=len(response_text),
                    estimated_read_time=f"{max(1, len(response_text) // 200)} minutes",
                    included_sections={"overview": True},
                    quality_checks={"completeness": 50, "clarity": 50, "user_friendly": 50},
                    cleanup_log={"status": "safe_fallback"},
                    reasoning="Fallback writer result created because response did not match the expected schema."
                )

            # Extract final output
            final_output = writing_result.final_output
            
            self.trace_recorder.record_event(
                phase="writing",
                agent=self.agent_name,
                event_type="output_generated",
                data={
                    "character_count": len(final_output),
                    "read_time": writing_result.estimated_read_time
                }
            )
            
            # Perform cleanup
            cleanup_log = self._cleanup_workflow()
            
            self.trace_recorder.record_event(
                phase="writing",
                agent=self.agent_name,
                event_type="cleanup_completed",
                data=cleanup_log
            )
            
            # Update communication file with final output
            self.comm_manager.update_phase(
                "writing",
                "completed",
                {
                    "research_data": research_data,
                    "final_output": final_output,
                    "formatting_applied": writing_result.formatting_applied
                }
            )
            
            total_duration = (time.time() - start_time) * 1000
            
            self.trace_recorder.record_event(
                phase="writing",
                agent=self.agent_name,
                event_type="writing_completed",
                metadata={"total_duration_ms": total_duration}
            )
            
            return {
                "status": "success",
                "final_output": final_output,
                "output_metadata": writing_result.model_dump(),
                "cleanup": cleanup_log,
                "duration_ms": total_duration
            }
            
        except Exception as e:
            logger.error(f"Error in writing: {e}")
            self.trace_recorder.record_error(
                phase="writing",
                agent=self.agent_name,
                error=str(e)
            )
            
            return {
                "status": "error",
                "error": str(e),
                "duration_ms": (time.time() - start_time) * 1000
            }
    
    def _parse_writing_response(self, response_text: str) -> Dict[str, Any]:
        """Parse JSON from LLM response"""
        try:
            return json.loads(response_text)
        except json.JSONDecodeError:
            import re
            json_match = re.search(r'\{.*\}', response_text, re.DOTALL)
            if json_match:
                try:
                    return json.loads(json_match.group())
                except json.JSONDecodeError:
                    pass
            
            return {
                "status": "writing_complete",
                "final_output": response_text,
                "output_structure": ["full_response"],
                "formatting_applied": ["natural_language"],
                "character_count": len(response_text),
                "estimated_read_time": f"{max(1, len(response_text) // 200)} minutes"
            }
    
    def _cleanup_workflow(self) -> Dict[str, Any]:
        """Clean up workflow files"""
        return self.comm_manager.cleanup(reason="successful_completion")
