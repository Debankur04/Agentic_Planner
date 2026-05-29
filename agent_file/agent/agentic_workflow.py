from langchain_core.messages import SystemMessage, ToolMessage, HumanMessage
import json
from langgraph.graph import StateGraph, MessagesState, END, START
from langgraph.checkpoint.memory import MemorySaver
from langchain_core.tools import tool
from langchain_core.messages import AIMessage
from llmops.token_tracker import *
from agent_file.utils.model_loader import *
from agent_file.prompt_library.prompt import SYSTEM_PROMPT
from agent_file.prompt_library.prompt_maker import *
from fastapi import HTTPException
from typing import Dict, Any, List
from datetime import datetime
import time
import uuid
import asyncio
import logging
from agent_file.utils.communication_manager import CommunicationManager, TraceRecorder, WorkflowOrchestrator

logger = logging.getLogger(__name__)
from agent_file.agent.multi_agents import (
    IntakeValidatorAgent,
    ResearchPricingAgent,
    WriterAgent
)
from agent_file.agent.exceptions import MissingStateError, NodeExecutionError, WorkflowExecutionError, StateValidationError, SerializationError
from agent_file.schemas import (
    WorkflowState,
    ValidationResult,
    ResearchResult,
    WriterResult,
    create_workflow_state,
    calculate_state_completeness
)
from agent_file.utils.serialization import safe_jsonable_encoder
from agent_file.utils.state_utils import safe_to_dict


def ensure_valid_node_output(result: Any, node_name: str) -> dict:
    if not isinstance(result, dict):
        raise NodeExecutionError(node_name, result)
    return result


def dump_state_snapshot(state: Any) -> str:
    try:
        normalized_state = safe_to_dict(state)
        return json.dumps(safe_jsonable_encoder(normalized_state), indent=2, ensure_ascii=False)
    except Exception:
        return repr(state)


def safe_node(node_name: str):
    def decorator(func):
        def wrapper(self, state: MessagesState, config: dict = None):
            config = config or {}
            trace = config.get("configurable", {}).get("trace")
            start = time.time()
            logger = logging.getLogger(__name__)
            state_keys = list(state.keys()) if hasattr(state, "keys") else []
            logger.info(f"ENTER NODE: {node_name}")
            logger.info(f"STATE KEYS AVAILABLE: {state_keys}")
            if trace:
                trace.record(node_name, {"status": "starting", "state_keys": state_keys})
            try:
                result = func(self, state, config)
                result = ensure_valid_node_output(result, node_name)
                duration_ms = int((time.time() - start) * 1000)
                updated_keys = list(result.keys()) if isinstance(result, dict) else []
                logger.info(f"EXIT NODE: {node_name}")
                logger.info(f"UPDATED KEYS: {updated_keys}")
                if trace:
                    trace.record(node_name, {"status": "success", "updated_keys": updated_keys}, latency_ms=duration_ms)
                return result
            except Exception as exc:
                duration_ms = int((time.time() - start) * 1000)
                error_payload = {"status": "failed", "error": str(exc), "state_snapshot": dump_state_snapshot(state)}
                logger.error(f"NODE FAILED: {node_name}: {str(exc)}")
                if trace:
                    trace.record(node_name, error_payload, latency_ms=duration_ms)
                raise
        return wrapper
    return decorator

# ✅ Tools
from agent_file.tools.flight_search import get_flight_search_tool
from agent_file.tools.hotel_search import get_hotel_search_tool
from agent_file.tools.place_search_tool import get_place_search_tools
from agent_file.tools.weather_info_tool import get_weather_tools
from agent_file.tools.railway_search import get_railway_search_tool

from service.cache_service import *
import concurrent.futures
from llmops.trace_service import ExecutionTrace
from agent_file.prompt_library.prompt_maker import fallback_json


# Lightweight in-memory communication manager used during agent local runs.
class InMemoryCommunicationManager:
    def __init__(self):
        self._state = {
            "intake_validation": {},
            "research_pricing": {},
            "writing": {},
            "global_trace": [],
            "metadata": {}
        }

    def read_state(self):
        return self._state

    def write_state(self, state):
        self._state = state
        return True

    def update_phase(self, phase: str, status: str, data: Dict[str, Any] = None) -> bool:
        self._state.setdefault(phase, {})
        self._state[phase]["status"] = status
        if data:
            self._state[phase].update(data)
        return True

    def add_trace_log(self, phase: str, agent: str, event: str, data: Dict[str, Any] = None) -> bool:
        entry = {"phase": phase, "agent": agent, "event": event, "data": data or {}, "timestamp": datetime.utcnow().isoformat()}
        self._state.setdefault("global_trace", []).append(entry)
        return True

    def save_agent_output(self, phase: str, key: str, data: Any) -> bool:
        self._state.setdefault(phase, {})[key] = data
        return True

    def get_agent_input(self, phase: str, key: str) -> Any:
        return self._state.get(phase, {}).get(key)

    def initialize_workflow(self, workflow_id: str, user_id: str, conversation_id: str, request_id: str, user_input: str) -> bool:
        self._state["metadata"].update({"workflow_id": workflow_id, "user_id": user_id, "conversation_id": conversation_id, "request_id": request_id})
        self._state.setdefault("intake_validation", {})["user_input"] = user_input
        return True

    def cleanup(self, reason: str = "normal_completion") -> Dict[str, Any]:
        return {"status": "success", "reason": reason, "timestamp": datetime.utcnow().isoformat()}

    def get_workflow_summary(self) -> Dict[str, Any]:
        return {"metadata": self._state.get("metadata", {}), "phases": {k: v.get("status") for k, v in self._state.items() if isinstance(v, dict)}}


# Local trace recorder that writes only to memory (no file/redis writes)
class LocalTraceRecorder:
    def __init__(self, comm_manager: InMemoryCommunicationManager = None):
        self.events = []
        self.comm_manager = comm_manager
        self.start_time = time.time()
        # lazy-initialize trace persister
        self._trace_persist = None

    def record_event(self, phase: str, agent: str, event_type: str, data: Dict[str, Any] = None, metadata: Dict[str, Any] = None) -> None:
        event = {"timestamp": datetime.utcnow().isoformat(), "phase": phase, "agent": agent, "event_type": event_type, "data": data or {}, "metadata": metadata or {}}
        self.events.append(event)
        if self.comm_manager:
            self.comm_manager.add_trace_log(phase, agent, event_type, data)

    def record_tool_call(self, phase: str, agent: str, tool_name: str, tool_args: Dict[str, Any], result: Any, duration_ms: float, cache_hit: bool = False) -> None:
        self.record_event(phase, agent, "tool_call", {"tool_name": tool_name, "args": str(tool_args)[:200], "result_preview": str(result)[:200], "cache_hit": cache_hit}, metadata={"duration_ms": duration_ms})

    def record_error(self, phase: str, agent: str, error: str, error_details: str = None) -> None:
        self.record_event(phase, agent, "error", {"error": error, "details": error_details or ""})

    def record_decision(self, phase: str, agent: str, decision: str, reasoning: str, alternatives: List[str] = None) -> None:
        self.record_event(phase, agent, "decision", {"decision": decision, "reasoning": reasoning, "alternatives": alternatives or []})

    def get_trace_summary(self) -> Dict[str, Any]:
        return {"total_events": len(self.events), "events": self.events}

    async def persist_to_redis(self, workflow_id: str, redis_url: str = None):
        try:
            from agent_file.orchestrator.trace_persist import TracePersist
            if self._trace_persist is None:
                self._trace_persist = TracePersist(redis_url)
            await self._trace_persist.persist_trace_events(workflow_id, self.events)
        except Exception:
            # best-effort
            pass


def run_with_timeout(app, input_data, config):
    with concurrent.futures.ThreadPoolExecutor() as executor:
        future = executor.submit(app.invoke, input_data, config)
        try:
            return future.result(timeout=30)
        except concurrent.futures.TimeoutError:
            raise HTTPException(408, detail="Request timeout (30s)")

token_tracker = TokenTracker(redis_client=redis_client)

class GraphBuilder:
    def __init__(self, router):
        self.router = router

        search_attractions, search_restaurants, search_activities, search_transportation = get_place_search_tools()
        find_flights = get_flight_search_tool()
        search_hotel = get_hotel_search_tool()
        get_current_weather, get_weather_forecast = get_weather_tools()
        find_routes, estimate_delay, live_train_update, get_schedule, get_code_station = get_railway_search_tool()

        @tool
        def ask_human(question: str) -> str:
            """Ask the user a question to clarify missing critical information (e.g., travel dates, preferences, budget)."""
            pass

        self.tools = [
            find_flights,
            search_hotel,
            search_attractions,
            search_restaurants,
            search_activities,
            search_transportation,
            get_current_weather,
            get_weather_forecast,
            find_routes,
            estimate_delay,
            live_train_update,
            get_schedule,
            get_code_station,
            ask_human
        ]
        self.tool_map = {tool.name: tool for tool in self.tools}
        self.system_prompt = SYSTEM_PROMPT

    def _get_default_workflow_state(self, user_input: str = "") -> Dict[str, Any]:
        return {
            "workflow_id": None,
            "user_input": user_input,
            "current_agent": None,
            "tool_results": {},
            "trace_events": [],
            "last_response_preview": None,
            "status": "pending"
        }

    # ------------------ AGENT NODE ------------------
    @safe_node("agent")
    def agent_function(self, state: MessagesState, config: dict = None):
        config = config or {}
        messages = state["messages"]  # ✅ FIX: preserve full history

        user_message = messages[-1].content
        preference = state.get("preference", "")
        history = state.get("history", "")
        memory = state.get("memory", "")
        user_id = state.get("user_id", "")
        trace = config.get("configurable", {}).get("trace")

        if trace:
            trace.record("agent_node_start", {"model_selection": "pending"})

        # Ensure LangGraph state contains a compact workflow_state the orchestrator can own
        if "workflow_state" not in state:
            state["workflow_state"] = self._get_default_workflow_state(user_input=user_message)

        # Mark active agent for observability
        state["workflow_state"]["current_agent"] = "agent_node"
        if trace:
            trace.record("state_update", {"stage": "agent_node_start", "workflow_preview": str(state["workflow_state"])[:300]})

        # ✅ Only inject system prompt ONCE
        if not any(isinstance(m, SystemMessage) for m in messages):
            prompt_messages = prompt_creation(
                system_prompt=self.system_prompt,
                preference=preference,
                history=history,
                input_question=user_message,
                memory=memory
            )
            messages = prompt_messages + messages

        if not token_tracker.check_budget(user_id, user_tier='free'):
            raise HTTPException(429, detail={
            "error": "daily_budget_exceeded",
            "message": "You've reached your daily AI usage limit. Upgrade to continue.",
            "reset_at": "midnight UTC"
        })

        attempted = set()

        while True:
            try:
                model_key = self.router.select_model(user_message, exclude_models=attempted)
            except RuntimeError:
                raise HTTPException(500, "All models exhausted")

            if model_key in attempted:
                raise HTTPException(500, "All models exhausted")

            # --- retry: log when we loop back after a failure ---
            if attempted:
                if trace:
                    trace.record("llm_retry", {
                        "retry_model": model_key,
                        "already_tried": list(attempted)
                    })

            attempted.add(model_key)

            # 1. Model selected
            if trace:
                trace.record("model_selected", {
                    "model_key": model_key,
                    "model_name": self.router.config["models"][model_key]["model_name"],
                    "provider": self.router.config["models"][model_key]["provider"]
                })

            try:
                client = self.router.get_client(model_key)

                # 2. Client initialised
                if trace:
                    trace.record("client_initialized", {"model_key": model_key})

                llm = client.bind_tools(self.tools)

                # 3. Tools bound
                if trace:
                    trace.record("tools_bound", {
                        "model_key": model_key,
                        "tools": [t.name for t in self.tools]
                    })

                # 4. LLM invocation start
                if trace:
                    trace.record("llm_invoke_start", {
                        "model_key": model_key,
                        "message_count": len(messages)
                    })

                start = time.time()
                
                response = llm.invoke(messages)
                latency = (time.time() - start) * 1000

                # 5. LLM invocation success
                self.router.record_success(model_key, latency)
                if trace:
                    trace.record("llm_invoke_success", {
                        "model": model_key,
                        "response_preview": str(getattr(response, "content", ""))[:200],
                        "has_tool_calls": bool(getattr(response, "tool_calls", None))
                    }, latency_ms=latency)

                break

            except Exception as e:
                # 6. LLM invocation error
                self.router.record_failure(model_key, e)
                if trace:
                    trace.record("llm_invoke_error", {"model": model_key, "error": str(e)})

        model = self.router.config["models"][model_key]["model_name"] 
        usage_data = getattr(response, "usage", None)

        if usage_data:
            usage = TokenUsage(
            input_tokens=usage_data.prompt_tokens,
            output_tokens=usage_data.completion_tokens,
            model=model  # or dynamically from config
        )

            token_tracker.record_usage(user_id, usage)

        print("\n🧠 LLM RESPONSE:", response)
        print("🛠 TOOL CALLS:", getattr(response, "tool_calls", None))

        # Best-effort: write a compact preview of the response into workflow_state.
        try:
            preview = str(getattr(response, "content", ""))[:1000]
            ws = state.setdefault("workflow_state", self._get_default_workflow_state(user_input=user_message))
            ws["last_response_preview"] = preview
        except Exception:
            pass

        # Clear active marker and emit trace
        try:
            state["workflow_state"]["current_agent"] = None
            if trace:
                trace.record("state_update", {"stage": "agent_node_end", "last_preview": state["workflow_state"].get("last_response_preview")})
        except Exception:
            pass

        return {
            "messages": state["messages"] + [response]
        }

    # ------------------ TOOL NODE ------------------
    @safe_node("tool")
    def tool_node(self, state: MessagesState, config: dict = None):
        config = config or {}
        last_message = state["messages"][-1]
        trace = config.get("configurable", {}).get("trace")
        outputs = []
        # Ensure workflow_state exists and mark active agent
        if "workflow_state" not in state:
            state["workflow_state"] = self._get_default_workflow_state(user_input="")
        state["workflow_state"]["current_agent"] = "tool_node"
        if hasattr(last_message, "tool_calls") and last_message.tool_calls:

            for tool_call in last_message.tool_calls:
                tool_name = tool_call["name"]
                args = tool_call["args"]

                print(f"\n🔥 EXECUTING TOOL: {tool_name}")
                print(f"📦 ARGS: {args}")

                # tool_called — before any execution
                if trace:
                    trace.record("tool_called", {
                        "tool": tool_name,
                        "args": str(args)[:300]   # truncate large payloads
                    })

                cache_key = make_cache_key(tool_name, args)
                cached = get_cache(cache_key)

                if cached:
                    print(f"⚡ CACHE HIT: {tool_name}")
                    result = cached
                    if trace:
                        trace.record("tool_cache_hit", {"tool": tool_name})
                else:
                    print(f"🔥 CACHE MISS: {tool_name}")

                    if tool_name in self.tool_map:
                        try:
                            t0 = time.time()
                            result = self.tool_map[tool_name].invoke(args)
                            t1 = (time.time() - t0) * 1000

                            # tool_success — after successful execution
                            if trace:
                                trace.record("tool_success", {
                                    "tool": tool_name,
                                    "result_preview": str(result)[:200]
                                }, latency_ms=t1)

                            # handle API-level errors inside result
                            if isinstance(result, dict) and "error" in result:
                                result = "Tool failed. Continue with available data."
                            else:
                                set_cache(cache_key, result, ttl=300)

                        except Exception as e:
                            result = f"Tool error: {str(e)}"
                            # tool_error — exception during execution
                            if trace:
                                trace.record("tool_error", {
                                    "tool": tool_name,
                                    "error": str(e)
                                })
                            # record failed tool into workflow_state for observability
                            try:
                                state["workflow_state"]["tool_results"][tool_name] = {"error": str(e)}
                                if trace:
                                    trace.record("state_update", {"stage": "tool_error_recorded", "tool": tool_name})
                            except Exception:
                                pass
                    else:
                        result = "Tool not found"

                print(f"✅ RESULT: {result}")

                outputs.append(
                    ToolMessage(
                        content=str(result),
                        tool_call_id=tool_call["id"]
                    )
                )

        # Clear active marker
        try:
            state["workflow_state"]["current_agent"] = None
        except Exception:
            pass

        return {
            "messages": state["messages"] + outputs
        }

    # ------------------ ASK HUMAN NODE ------------------
    def ask_human_node(self, state: MessagesState):
        # The graph pauses BEFORE this node.
        # When resumed, the state is already updated with the user's answer (ToolMessage)
        pass

    # ------------------ ROUTING ------------------
    def should_continue(self, state: MessagesState):
        messages = state["messages"]
        last_message = messages[-1]

        # If no tool calls are present, end the graph.
        if not hasattr(last_message, "tool_calls") or not last_message.tool_calls:
            return "end"

        # If the model explicitly asked for user input, pause and ask.
        if any(tc["name"] == "ask_human" for tc in last_message.tool_calls):
            return "ask_human_node"

        # Stop runaway loops after a fixed number of steps.
        if len(messages) > 15:
            print("⚠️ Max steps reached. Stopping loop.")
            return "end"

        # Prevent repeating the same tool call over and over.
        tool_calls = [m for m in messages if isinstance(m, ToolMessage)]
        tool_names = [t.content for t in tool_calls]
        if len(tool_names) != len(set(tool_names)):
            print("⚠️ Repeated tool detected. Stopping loop.")
            return "end"

        return "tool"

    # ------------------ BUILD GRAPH ------------------
    def build(self):
        graph = StateGraph(MessagesState)

        graph.add_node("agent", self.agent_function)
        graph.add_node("tool", self.tool_node)
        graph.add_node("ask_human_node", self.ask_human_node)

        graph.add_edge(START, "agent")

        graph.add_conditional_edges(
            "agent",
            self.should_continue,
            {
                "tool": "tool",
                "ask_human_node": "ask_human_node",
                "end": END
            }
        )

        graph.add_edge("tool", "agent")
        graph.add_edge("ask_human_node", "agent")

        self.checkpointer = MemorySaver()
        return graph.compile(checkpointer=self.checkpointer, interrupt_before=["ask_human_node"])


class AgentRunner:
    def __init__(self, router):
        agent = GraphBuilder(router)
        self.app = agent.build()    
        self.summary_llm = load_summarizier_llm()
        self.fallback_json_llm = load_fallback_to_json_llm()



    def run_agent(self, user_input, preference="", history="", memory="", user_id='', request_id: str = None, conversation_id: str = None):
        trace = ExecutionTrace(request_id=request_id)
        trace.record("run_agent_start", {"user_input": user_input[:300], "user_id": user_id})
        t0 = time.time()
        
        config = {"configurable": {
            "thread_id": conversation_id or "default",
            "trace": trace
        }}

        try:
            state = self.app.get_state(config)
            
            if state and state.next and "ask_human_node" in state.next:
                # We are paused waiting for user input
                last_msg = state.values["messages"][-1]
                tool_call = next(tc for tc in last_msg.tool_calls if tc["name"] == "ask_human")
                
                tool_msg = ToolMessage(
                    tool_call_id=tool_call["id"],
                    name="ask_human",
                    content=user_input
                )
                self.app.update_state(config, {"messages": [tool_msg]}, as_node="ask_human_node")
                
                output = run_with_timeout(self.app, None, config=config)
            else:
                output = run_with_timeout(self.app, {
                    "messages": [HumanMessage(content=user_input)],
                    "preference": preference,
                    "history": history,
                    "memory": memory,
                    "user_id": user_id
                }, config=config)

            # Check if it paused again
            state = self.app.get_state(config)
            if state and state.next and "ask_human_node" in state.next:
                # It just hit an interrupt, we need to return the question to the user
                last_msg = state.values["messages"][-1]
                tool_call = next(tc for tc in last_msg.tool_calls if tc["name"] == "ask_human")
                question = tool_call["args"].get("question", "Could you provide more details?")
                    
                # Append an AIMessage so the controller extracts the question correctly
                output["messages"] = list(output["messages"]) + [AIMessage(content=question, additional_kwargs={"is_hitl": True})]

            # Capture the final response for tracing
            final_msg = None
            for msg in reversed(output["messages"]):
                if not isinstance(msg, ToolMessage):
                    final_msg = msg
                    break
            trace.record(
                "final_response",
                {"response_preview": str(getattr(final_msg, "content", ""))[:200]},
                latency_ms=(time.time() - t0) * 1000
            )

            trace.record("run_agent_end", {"status": "success"}, latency_ms=(time.time()-t0)*1000)
            return output
        except Exception as e:
            trace.record("run_agent_error", {"error": str(e)}, latency_ms=(time.time()-t0)*1000)
            raise e
        finally:
            trace.save_to_db()
            trace.save_to_redis(redis_client)

    def summary_agent(self, history: str, user_message: str):
        prompt = summarize_history(history=history, user_message=user_message)
        new_history = self.summary_llm.invoke(prompt)
        return new_history.content.strip()
    
    def fallback_json_agent(self, raw_input):
        prompt = fallback_json(raw_output= raw_input)
        fallback = self.fallback_json_llm.invoke(prompt)
        return fallback

    def intake_validator_agent(self, user_input: str, user_id: str, 
                              conversation_id: str, request_id: str,
                              custom_prompt: str = None):
        """
        Phase 1: Simple intake validation
        Returns: {"status": "success", "validation": {"initial_plan": "text or dict"}}
        """
        try:
            # Just call the LLM to create an initial plan
            from langchain_core.messages import SystemMessage, HumanMessage
            
            system_msg = custom_prompt or (
                "You are an intake validation agent. "
                "Analyze the user input and create a brief initial plan. "
                "Return ONLY valid JSON with: {\"initial_plan\": \"<text>\", \"confidence\": 80}"
            )
            
            user_msg = f"User ID: {user_id}\nInput: {user_input}"
            
            response = self.summary_llm.invoke([
                SystemMessage(content=system_msg),
                HumanMessage(content=user_msg)
            ])
            
            # Parse response
            response_text = response.content
            try:
                parsed = json.loads(response_text)
            except:
                import re
                match = re.search(r'\{.*\}', response_text, re.DOTALL)
                if match:
                    try:
                        parsed = json.loads(match.group())
                    except:
                        parsed = {"initial_plan": response_text}
                else:
                    parsed = {"initial_plan": response_text}
            
            return {
                "workflow_id": request_id,
                "phase": "intake_validation",
                "result": {
                    "status": "success",
                    "validation": parsed if parsed.get("initial_plan") else {"initial_plan": str(parsed)},
                    "duration_ms": 0
                },
                "comm_manager": None,
                "trace_recorder": None
            }
        except Exception as e:
            return {
                "workflow_id": request_id,
                "phase": "intake_validation",
                "result": {
                    "status": "error",
                    "error": str(e),
                    "duration_ms": 0
                },
                "comm_manager": None,
                "trace_recorder": None
            }

    def research_pricing_agent(self, initial_plan: dict, context: dict,
                              custom_prompt: str = None, max_api_calls: int = 10):
        """
        Phase 2: Simple research and pricing
        Returns: {"status": "success", "research": {"findings": "text"}}
        """
        try:
            from langchain_core.messages import SystemMessage, HumanMessage
            
            system_msg = custom_prompt or (
                "You are a research agent. Based on the initial plan, "
                "conduct research and provide pricing options. "
                "Return ONLY valid JSON with: {\"findings\": \"<research>\", \"pricing\": {}, \"recommendations\": []}"
            )
            
            plan_text = json.dumps(initial_plan) if isinstance(initial_plan, dict) else str(initial_plan)
            user_query = context.get("user_query", "")
            
            user_msg = f"Initial Plan: {plan_text}\nUser Query: {user_query}"
            
            response = self.summary_llm.invoke([
                SystemMessage(content=system_msg),
                HumanMessage(content=user_msg)
            ])
            
            # Parse response
            response_text = response.content
            try:
                parsed = json.loads(response_text)
            except:
                import re
                match = re.search(r'\{.*\}', response_text, re.DOTALL)
                if match:
                    try:
                        parsed = json.loads(match.group())
                    except:
                        parsed = {"findings": response_text}
                else:
                    parsed = {"findings": response_text}
            
            return {
                "phase": "research_pricing",
                "result": {
                    "status": "success",
                    "research": parsed if parsed.get("findings") else {"findings": str(parsed)},
                    "api_calls_made": 0,
                    "duration_ms": 0
                },
                "comm_manager": None,
                "trace_recorder": None
            }
        except Exception as e:
            return {
                "phase": "research_pricing",
                "result": {
                    "status": "error",
                    "error": str(e),
                    "duration_ms": 0
                },
                "comm_manager": None,
                "trace_recorder": None
            }

    def writer_agent(self, research_data: dict, context: dict,
                    custom_prompt: str = None):
        """
        Phase 3: Simple writer agent
        Returns: {"status": "success", "final_output": "text"}
        """
        try:
            from langchain_core.messages import SystemMessage, HumanMessage
            
            system_msg = custom_prompt or (
                "You are a writer agent. Based on the research data, "
                "write a clear, well-formatted response for the user. "
                "Return ONLY valid JSON with: {\"final_output\": \"<response>\", \"status\": \"writing_complete\"}"
            )
            
            research_text = json.dumps(research_data) if isinstance(research_data, dict) else str(research_data)
            user_query = context.get("user_query", "")
            
            user_msg = f"Research: {research_text[:500]}...\nUser Query: {user_query}"
            
            response = self.summary_llm.invoke([
                SystemMessage(content=system_msg),
                HumanMessage(content=user_msg)
            ])
            
            # Parse response
            response_text = response.content
            try:
                parsed = json.loads(response_text)
            except:
                import re
                match = re.search(r'\{.*\}', response_text, re.DOTALL)
                if match:
                    try:
                        parsed = json.loads(match.group())
                    except:
                        parsed = {"final_output": response_text}
                else:
                    parsed = {"final_output": response_text}
            
            final_output = parsed.get("final_output", str(parsed))
            if not final_output:
                final_output = response_text
            
            return {
                "phase": "writing",
                "result": {
                    "status": "success",
                    "final_output": str(final_output),
                    "output_metadata": parsed,
                    "cleanup": {},
                    "duration_ms": 0
                },
                "comm_manager": None,
                "trace_recorder": None
            }
        except Exception as e:
            return {
                "phase": "writing",
                "result": {
                    "status": "error",
                    "error": str(e),
                    "final_output": "",
                    "duration_ms": 0
                },
                "comm_manager": None,
                "trace_recorder": None
            }

class MultiAgentEngine:
    """
    Orchestrates the three-phase multi-agent workflow:
    Phase 1: Intake Validator
    Phase 2: Research & Pricing
    Phase 3: Writer
    """
    
    def __init__(self, agent_runner: AgentRunner):
        self.agent_runner = agent_runner
    
    def process_with_multi_agents(
        self,
        user_input: str,
        user_id: str,
        preference: str = "",
        history: str = "",
        memory: str = "",
        conversation_id: str = None,
        custom_prompts: dict = None
    ) -> dict:
        """
        Process user input through three simple text-passing agents:
        Phase 1: Intake → returns initial_plan (text)
        Phase 2: Research → returns research_data (text)
        Phase 3: Writing → returns final_output (text)
        """
        if not user_input or not str(user_input).strip():
            raise ValueError("user_input is required and cannot be empty")

        try:
            print(f"\n📋 PHASE 1: INTAKE VALIDATION")
            print(f"{'='*60}")
            
            # ============ PHASE 1: INTAKE - Just validate and create initial plan ============
            intake_result = self.agent_runner.intake_validator_agent(
                user_input=user_input,
                user_id=user_id,
                conversation_id=conversation_id or f"conv_{user_id}_{int(time.time())}",
                request_id=str(uuid.uuid4()),
                custom_prompt=custom_prompts.get("intake_validation") if custom_prompts else None
            )
            
            if intake_result["result"]["status"] != "success":
                return {
                    "status": "error",
                    "phase": "intake_validation",
                    "error": intake_result["result"].get("error", "Unknown error"),
                    "final_output": ""
                }
            
            # Extract initial plan as text (not a complex object)
            initial_plan = intake_result["result"].get("validation", {}).get("initial_plan", "")
            if isinstance(initial_plan, dict):
                initial_plan = json.dumps(initial_plan)
            initial_plan = str(initial_plan)
            
            print(f"✅ Intake complete. Plan: {initial_plan[:100]}...")

            # ============ PHASE 2: RESEARCH - Pass initial plan and get research data ============
            print(f"\n🔍 PHASE 2: RESEARCH & PRICING")
            print(f"{'='*60}")
            
            research_result = self.agent_runner.research_pricing_agent(
                initial_plan={"estimated_steps": [initial_plan]},  # Simple dict
                context={
                    "user_id": user_id,
                    "user_query": user_input,
                    "preference": preference,
                    "history": history,
                    "memory": memory
                },
                custom_prompt=custom_prompts.get("research_pricing") if custom_prompts else None,
                max_api_calls=10
            )
            
            if research_result["result"]["status"] != "success":
                return {
                    "status": "error",
                    "phase": "research_pricing",
                    "error": research_result["result"].get("error", "Unknown error"),
                    "final_output": ""
                }
            
            # Extract research data as text
            research_data = research_result["result"].get("research", {})
            if isinstance(research_data, dict):
                research_text = json.dumps(research_data)
            else:
                research_text = str(research_data)
            
            print(f"✅ Research complete. Data length: {len(research_text)} chars")

            # ============ PHASE 3: WRITING - Pass research and get final output ============
            print(f"\n📝 PHASE 3: WRITING")
            print(f"{'='*60}")
            
            writing_result = self.agent_runner.writer_agent(
                research_data=research_data if isinstance(research_data, dict) else {"raw": research_text},
                context={
                    "user_id": user_id,
                    "user_query": user_input,
                    "preference": preference,
                    "output_format": "markdown",
                    "audience": "general",
                    "tone": "professional"
                },
                custom_prompt=custom_prompts.get("writing") if custom_prompts else None
            )
            
            if writing_result["result"]["status"] != "success":
                return {
                    "status": "error",
                    "phase": "writing",
                    "error": writing_result["result"].get("error", "Unknown error"),
                    "final_output": ""
                }
            
            # Extract final output as text
            final_output = writing_result["result"].get("final_output", "")
            final_output = str(final_output).strip()
            
            if not final_output:
                return {
                    "status": "error",
                    "phase": "writing",
                    "error": "Final output is empty",
                    "final_output": ""
                }
            
            print(f"✅ Writing complete. Output length: {len(final_output)} chars")
            
            return {
                "status": "success",
                "final_output": final_output,
                "phases": {
                    "intake_validation": {"status": "completed"},
                    "research_pricing": {"status": "completed"},
                    "writing": {"status": "completed"}
                }
            }

        except Exception as e:
            import traceback
            logger.error("WORKFLOW ERROR: %s", str(e), exc_info=True)
            return {
                "status": "error",
                "error": str(e),
                "error_traceback": traceback.format_exc(),
                "final_output": ""
            }

    def summary_agent(self, history: str, user_message: str):
        return self.agent_runner.summary_agent(history, user_message)

class TravelEngine:
    def __init__(self, agent_runner: MultiAgentEngine):
        self.agent_runner = agent_runner

    def process_query(self, user_input, preference="", history="", memory="", user_id ="", conversation_id="", streaming_callback=None):
        if not user_id:
            raise ValueError("user_id required")

        output = None
        if hasattr(self.agent_runner, "process_with_multi_agents"):
            output = self.agent_runner.process_with_multi_agents(
                user_input=user_input,
                user_id=user_id,
                preference=preference,
                history=history,
                memory=memory,
                conversation_id=conversation_id
            )

            if not isinstance(output, dict):
                raise WorkflowExecutionError("Multi-agent engine returned invalid output type", details={"output_type": type(output).__name__})

            if output.get("status") != "success":
                raise WorkflowExecutionError(
                    "Multi-agent workflow failed",
                    details={
                        "status": output.get("status"),
                        "phase": output.get("phase"),
                        "error": output.get("error"),
                        "workflow_summary": output.get("workflow_summary")
                    }
                )

            if "final_output" not in output:
                raise WorkflowExecutionError("Multi-agent engine did not return a final_output", details=output)

            reply = str(output.get("final_output", ""))
            pref = None
            is_hitl = False
            if len(history) > 300 and hasattr(self.agent_runner, "summary_agent"):
                history = self.agent_runner.summary_agent(history, f"user query: {user_input}\nagent reply: {reply}")
            else:
                history += f"\nuser query: {user_input}\nagent reply: {reply}"
            return reply, pref, history, is_hitl
        else:
            output = self.agent_runner.run_agent(
                user_input=user_input,
                preference=preference,
                history=history,
                memory=memory,
                user_id=user_id,
                request_id=conversation_id,
                conversation_id=conversation_id
            )

        # ✅ FIX: get last AI message (not tool message)
        response = None
        is_hitl = False
        if not isinstance(output, dict) or "messages" not in output:
            raise WorkflowExecutionError("LLM agent run returned invalid output", details={"output": output})
        for msg in reversed(output["messages"]):
            if not isinstance(msg, ToolMessage):
                response = msg.content
                if hasattr(msg, "additional_kwargs") and msg.additional_kwargs.get("is_hitl"):
                    is_hitl = True
                
                # Check if it was forcibly stopped without content but with tool calls
                if not response and hasattr(msg, "tool_calls") and msg.tool_calls:
                    response = "I've explored multiple options but couldn't finalize a complete itinerary within the search limit. Could you please provide more specific preferences (like exact dates or transport modes) so I can narrow down the search?"
                break

        if is_hitl:
            # If asking a clarification question, STOP immediately, don't generate any further text
            return response, preference, history, is_hitl

        content = self._parse_response(response)

        reply = self._extract_reply(content)
        pref = self._extract_preference(content)

        convo = f"""user query: 
                {user_input} 
                agent reply: 
                {reply}"""

        if len(history) > 300:
            history = self._summarizier(history=history, user_message=convo)
        else:
            history += convo

        return reply, pref, history, is_hitl

    def _parse_response(self, response):
        try:
            return json.loads(response) if isinstance(response, str) else response
        except:
            return response

    def _extract_reply(self, content):
        if isinstance(content, dict) and "reply" in content:
            return content["reply"]
        return str(content)

    def _extract_preference(self, content):
        if isinstance(content, dict) and content.get("confidence", 0) >= 80:
            return content.get("preference")
        return None

    def _summarizier(self, history, user_message):
        history = self.agent_runner.summary_agent(history, user_message)
        return history