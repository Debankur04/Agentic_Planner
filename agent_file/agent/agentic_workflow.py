from langchain_core.messages import SystemMessage, ToolMessage, HumanMessage
import json
from langgraph.graph import StateGraph, MessagesState, END, START, add_messages
from langchain_core.messages import AIMessage
from llmops.token_tracker import *
from agent_file.utils.model_loader import *
from agent_file.prompt_library.prompt_maker import *
from fastapi import HTTPException
from typing import Dict, Any, Annotated, TypedDict
import time
import logging
from agent_file.prompt_library.multi_agent_prompts import build_intake_prompt, build_research_prompt, build_writer_prompt

from agent_file.tools.flight_search import get_flight_search_tool
from agent_file.tools.hotel_search import get_hotel_search_tool
from agent_file.tools.place_search_tool import get_place_search_tools
from agent_file.tools.weather_info_tool import get_weather_tools
from agent_file.tools.railway_search import get_railway_search_tool

from service.cache_service import *
import concurrent.futures
from llmops.trace_service import ExecutionTrace
from agent_file.prompt_library.prompt_maker import fallback_json
from llmops.reliable_gateway import ReliableModelGateway, ModelInvocationError
import contextvars

logger = logging.getLogger(__name__)
token_tracker = TokenTracker(redis_client=redis_client)

def merge_dicts(left: dict, right: dict) -> dict:
    return {**left, **right}

def run_with_timeout(app, input_data, config):
    ctx = contextvars.copy_context()
    with concurrent.futures.ThreadPoolExecutor() as executor:
        future = executor.submit(ctx.run, app.invoke, input_data, config)
        try:
            return future.result(timeout=120)
        except concurrent.futures.TimeoutError:
            raise HTTPException(408, detail="Request timeout (120s)")

class AgentState(TypedDict):
    messages: Annotated[list, add_messages]
    workflow_state: Annotated[dict, merge_dicts]
    user_id: str
    preference: str
    history: str
    memory: str
    context_bundle: dict
    user_tier: str



class GraphBuilder:
    def __init__(self, router):
        self.router = router
        self.gateway = ReliableModelGateway(router)

        search_attractions, search_restaurants, search_activities, search_transportation = get_place_search_tools()
        find_flights = get_flight_search_tool()
        search_hotel = get_hotel_search_tool()
        get_current_weather, get_weather_forecast = get_weather_tools()
        find_routes, estimate_delay, live_train_update, get_schedule, get_code_station = get_railway_search_tool()

        self.intake_tools = []
        self.research_tools = [
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
        ]
        self.tool_map = {tool.name: tool for tool in self.research_tools + self.intake_tools}

    def _get_default_workflow_state(self, user_input: str = "") -> Dict[str, Any]:
        return {
            "user_input": user_input,
            "tool_results": {},
            "clarification_history": {},
            "ask_human_blocked": False,
            "phase": "",
            "planning_output": "",
            "research_output": "",
            "validation_output": {},
            "writer_output": "",
            "final_user_response": "",
            "workflow_status": "started",
        }

    def _append_state_response(self, state, response, agent_name):
        # Append the agent response to the existing messages list
        existing = state.get("messages", []) or []
        return {
            **state,
            "messages": existing + [response],
        }

    def _invoke_llm(self, prompt_messages: list, state: MessagesState, config: dict, agent_name: str, tools: list):
        trace = (config or {}).get("configurable", {}).get("trace")
        user_tier = state.get("user_tier", "Pirate")
        tool_names = [getattr(tool, "name", str(tool)) for tool in tools]
        if trace:
            trace.record("node_llm_invocation_start", {"node": agent_name, "tools": tool_names})
        return self.gateway.invoke_node(
            node_name=agent_name,
            prompt_messages=prompt_messages,
            tools=tools,
            trace=trace,
            user_tier=user_tier,
        )

    def _get_original_user_request(self, state: MessagesState) -> str:
        for message in reversed(state["messages"]):
            if isinstance(message, HumanMessage):
                return message.content
        return ""

    def _log_node_entry(self, node_name: str, state: MessagesState):
        try:
            msgs = state.get("messages", []) or []
            last_type = type(msgs[-1]).__name__ if msgs else "None"
            print("=" * 80)
            print("NODE:", node_name)
            print("MESSAGE COUNT:", len(msgs))
            print("LAST MESSAGE TYPE:", last_type)
            print("PHASE:", state.get("workflow_state", {}).get("phase"))
            print("=" * 80)
        except Exception as e:
            logger.debug("_log_node_entry failed: %s", e)

    def intake_node(self, state: AgentState, config: dict = None):
        config = config or {}
        self._log_node_entry("tool", state)
        original_request = self._get_original_user_request(state)
        state.setdefault("workflow_state", self._get_default_workflow_state(user_input=original_request))
        state["workflow_state"]["user_input"] = original_request
        state["workflow_state"]["phase"] = "intake"
        self._log_node_entry("intake", state)

        # research_result is stored as a raw string/object (not a dict with raw_output)
        research_output = state["workflow_state"].get("research_result", "")
        preference = state.get("preference", "")
        context_bundle = state.get("context_bundle", {}) or {}
        history = context_bundle.get("recent_messages_text", state.get("history", ""))
        memory = context_bundle.get("relevant_memory", state.get("memory", ""))
        
        system_prompt, user_prompt = build_intake_prompt(
            original_request,
            preference,
            history,
            memory,
            research_agent_input=research_output,
        )
        prompt_messages = [SystemMessage(content=system_prompt), HumanMessage(content=user_prompt)]

        response = self._invoke_llm(prompt_messages, state, config, agent_name="intake", tools=self.intake_tools)
        # Store raw content returned by the LLM directly (no JSON wrapping)
        state["workflow_state"]["intake_result"] = getattr(response, "content", "")
        state["workflow_state"]["planning_output"] = getattr(response, "content", "")
        if hasattr(response, "tool_calls") and response.tool_calls:
            state["workflow_state"]["intake_tool_calls"] = [tc["name"] for tc in response.tool_calls]

        return self._append_state_response(state, response, agent_name="intake")

    def research_node(self, state: AgentState, config: dict = None):
        print("RESEARCH STATE")
        print("KEYS:", state.keys())
        config = config or {}
        state["workflow_state"]["phase"] = "research"
        self._log_node_entry("research", state)
        state["workflow_state"]["research_iterations"] = (
        state["workflow_state"].get("research_iterations", 0) + 1
)

        user_input = state["workflow_state"].get("user_input", self._get_original_user_request(state))
        clarification_history = state["workflow_state"].get("clarification_history", {})
        clarification_answer = list(clarification_history.values())[-1] if clarification_history else ""
        # Use the raw intake output as-is. LLMs are responsible for producing JSON when needed.
        intake_output = state["workflow_state"].get(
            "intake_result",
            ""
        )
        if clarification_answer and "Clarification answer:" not in str(intake_output):
            if intake_output:
                intake_output = f"{intake_output}\nClarification answer: {clarification_answer}"
            else:
                intake_output = f"Clarification answer: {clarification_answer}"

        research_instructions = (
            f"User request: {user_input}\n"
            f"Intake plan:\n{intake_output}\n"
            "Use tools when appropriate to collect journey data, route options, fees, and weather information. "
            "If you can resolve the journey with the information available, do so. "
            "If a requested route is impossible, explain why and identify realistic alternatives."
        )
        system_prompt, user_prompt = build_research_prompt(
            user_input=user_input,
            intake_plan=intake_output,
            research_instructions=research_instructions,
            preference=state.get("preference", ""),
            history=(state.get("context_bundle", {}) or {}).get("recent_messages_text", state.get("history", "")),
            memory=(state.get("context_bundle", {}) or {}).get("relevant_memory", state.get("memory", "")),
            previous_tool_results=state.get("workflow_state", {}).get("tool_results", {}),
            clarification_history=state.get("workflow_state", {}).get("clarification_history", {}),
        )
        prompt_messages = [SystemMessage(content=system_prompt), HumanMessage(content=user_prompt)]
        tool_results = state["workflow_state"].get("tool_results", {})
        tools = []

        if not tool_results:
            tools = self.research_tools
        response = self._invoke_llm(
            prompt_messages,
            state,
            config,
            agent_name="research",
            tools=tools
        )
        research_text = getattr(response, "content", "")
        # Keep research result as raw content (string or object) without serializing
        state["workflow_state"]["research_result"] = research_text
        state["workflow_state"]["research_output"] = research_text
        state["workflow_state"]["validation_summary"] = research_text
        # Record any tool calls suggested by the research agent
        if hasattr(response, "tool_calls") and response.tool_calls:
            state["workflow_state"]["research_tool_calls"] = [tc["name"] for tc in response.tool_calls]

        return self._append_state_response(state, response,agent_name="research")

    def writer_node(self, state: AgentState, config: dict = None):
        config = config or {}
        state["workflow_state"]["phase"] = "writer"
        self._log_node_entry("writer", state)

        user_input = state["workflow_state"].get("user_input", "")
        validated_summary = (
    state["workflow_state"].get("validation_summary")
    or state["workflow_state"].get("research_result", "")
)
        context_bundle = state.get("context_bundle", {}) or {}
        system_prompt, user_prompt = build_writer_prompt(
            user_input,
            validated_summary,
            tool_results=state["workflow_state"].get("tool_results", {}),
            preference=state.get("preference", ""),
            relevant_memory=context_bundle.get("relevant_memory", state.get("memory", "")),
        )
        prompt_messages = [SystemMessage(content=system_prompt), HumanMessage(content=user_prompt)]

        response = self._invoke_llm(prompt_messages, state, config, agent_name="writer", tools=[])
        writer_output = getattr(response, "content", "")
        state["workflow_state"]["writer_output"] = writer_output
        state["workflow_state"]["final_user_response"] = writer_output
        state["workflow_state"]["workflow_status"] = "writer_completed"

        return self._append_state_response(state, response, agent_name="writer")

    def tool_node(self, state: MessagesState, config: dict = None):
        print("=" * 80)
        print("TOOL NODE ENTER")
        print("STATE KEYS:", state.keys())
        print("=" * 80)

        config = config or {}
        trace = config.get("configurable", {}).get("trace")

        outputs = []

        # ------------------------------------------------------------------
        # Ensure workflow_state exists
        # ------------------------------------------------------------------
        workflow_state = state.setdefault("workflow_state", {})

        # ------------------------------------------------------------------
        # Ensure tool_results exists
        # ------------------------------------------------------------------
        tool_results = workflow_state.setdefault("tool_results", {})

        last_message = state["messages"][-1]

        if hasattr(last_message, "tool_calls") and last_message.tool_calls:

            for tool_call in last_message.tool_calls:

                if tool_call["name"] == "ask_human":
                    continue

                tool_name = tool_call["name"]
                args = tool_call.get("args", {})

                print(f"\nTOOL: {tool_name}")
                print("ARGS:", args)

                # ----------------------------------------------------------
                # Cache lookup
                # ----------------------------------------------------------
                existing = tool_results.get(tool_name)

                if existing is not None:
                    print(f"USING CACHED RESULT FOR {tool_name}")

                    outputs.append(
                        ToolMessage(
                            content=str(existing),
                            tool_call_id=tool_call.get("id"),
                        )
                    )
                    continue

                # ----------------------------------------------------------
                # Execute tool
                # ----------------------------------------------------------
                logger.debug(
                    "Executing tool %s with args=%s",
                    tool_name,
                    args,
                )

                if trace:
                    trace.record(
                        "tool_called",
                        {
                            "tool": tool_name,
                            "args": str(args)[:300],
                        },
                    )

                result = self._execute_tool(
                    state,
                    tool_call,
                    trace,
                )

                logger.debug(
                    "Tool %s result: %s",
                    tool_name,
                    result,
                )

                # ----------------------------------------------------------
                # Store result into workflow_state
                # ----------------------------------------------------------
                tool_results[tool_name] = result

                outputs.append(
                    ToolMessage(
                        content=str(result),
                        tool_call_id=tool_call["id"],
                    )
                )

        print("\nTOOL RESULTS STORED:")
        print(tool_results.keys())

        print("=" * 80)
        print("TOOL NODE EXIT")
        print("=" * 80)

        return {
            **state,
            "messages": state.get("messages", []) + outputs,
            "workflow_state": workflow_state,
        }

    def _get_current_cycle_messages(self, messages):
        current = []

        for msg in reversed(messages):
            current.append(msg)

            if isinstance(msg, HumanMessage):
                break

        current.reverse()
        return current

    def _execute_tool(self, state: MessagesState, tool_call: dict, trace):
        tool_name = tool_call["name"]
        args = tool_call.get("args", {})
        cache_key = make_cache_key(tool_name, args)
        cached = get_cache(cache_key)
        if cached:
            if trace:
                trace.record("tool_cache_hit", {"tool": tool_name})
            return cached

        if tool_name not in self.tool_map:
            return "Tool not found"

        try:
            t0 = time.time()
            result = self.tool_map[tool_name].invoke(args)
            t1 = (time.time() - t0) * 1000
            if trace:
                trace.record("tool_success", {"tool": tool_name, "result_preview": str(result)[:200]}, latency_ms=t1)

            if isinstance(result, dict) and "error" in result:
                result = "Tool failed. Continue with available data."

            # persist tool result into workflow state for future research prompts
            state.setdefault("workflow_state", {}).setdefault("tool_results", {})
            try:
                state["workflow_state"]["tool_results"][tool_name] = result
            except Exception:
                state["workflow_state"]["tool_results"][tool_name] = str(result)

            set_cache(cache_key, result, ttl=300)
            return result
        except Exception as e:
            if trace:
                trace.record("tool_error", {"tool": tool_name, "error": str(e)})
            # Store tool error as plain string
            state["workflow_state"]["tool_results"][tool_name] = str(e)
            return f"Tool error: {str(e)}"

    def route_after_intake(self, state: AgentState):
        # ask_human is disabled in this test flow.
        return "research"

    def should_continue(self, state: AgentState):
        messages = state["messages"]
        last_message = messages[-1]

        print("SHOULD_CONTINUE")
        print("LAST MESSAGE:", type(last_message).__name__)

        if not (isinstance(last_message, AIMessage) and getattr(last_message, "tool_calls", None)):
            print("ROUTE = validator")
            return "validator"
        
        iterations = state["workflow_state"].get(
            "research_iterations",
            0
        )

        if iterations >= 10:
            logger.warning("Research iteration limit reached")
            return "validator"

        all_tool_signatures = []
        recent_messages = self._get_current_cycle_messages(messages)

        for m in recent_messages:
            if hasattr(m, "tool_calls") and m.tool_calls:
                for tc in m.tool_calls:
                    all_tool_signatures.append(self._tool_call_signature(tc))

        
        print("ALL TOOL SIGNATURES")
        for sig in all_tool_signatures:
            print(sig)

        if len(all_tool_signatures) != len(set(all_tool_signatures)):
            print("ROUTE = validator")
            logger.warning("Repeated tool call detected. Stopping loop.")
            return "validator"

        print("ROUTE = research_tool")
        return "research_tool"

    def route_after_validation(self, state: AgentState):
        decision = state.get("workflow_state", {}).get("validation_decision", "pass")
        if decision == "more_research":
            return "research"
        return "writer"

    def _tool_call_signature(self, tool_call: dict) -> tuple:
        args = tool_call.get("args")
        try:
            # Use simple string representation for args to avoid JSON serialization
            args_hash = str(args)
        except Exception:
            args_hash = repr(args)
        return (tool_call.get("name"), args_hash)

    def validator_node(self, state: AgentState, config: dict = None):
        state.setdefault(
        "workflow_state",
        self._get_default_workflow_state()
        )
        print("VALIDATOR IN")
        print(state["workflow_state"]["tool_results"].keys())
        config = config or {}
        

        state["workflow_state"]["phase"] = "validator"

        self._log_node_entry("validator", state)
        # Build a validation prompt using the intake validator template.
        original_request = state["workflow_state"].get("user_input", self._get_original_user_request(state))
        research_output = state["workflow_state"].get("research_result", "")
        preference = state.get("preference", "")
        history = state.get("history", "")
        memory = state.get("memory", "")
        context_bundle = state.get("context_bundle", {}) or {}
        history = context_bundle.get("recent_messages_text", history)
        memory = context_bundle.get("relevant_memory", memory)

        system_prompt, user_prompt = build_intake_prompt(
            original_request,
            preference,
            history,
            memory,
            research_agent_input=research_output,
            stage="validation",
        )
        prompt_messages = [SystemMessage(content=system_prompt), HumanMessage(content=user_prompt)]



        try:
            response = self._invoke_llm(prompt_messages, state, config, agent_name="validator", tools=[])
            raw = getattr(response, "content", "")
            # Try to parse structured JSON from the validator LLM
            try:
                parsed = json.loads(raw)
                decision = parsed.get("decision", "more_research")
            except Exception:
                # Fallback heuristic if JSON isn't returned
                text = str(raw).lower()
                if any(k in text for k in ["impossible", "cannot", "not possible", "no feasible"]):
                    decision = "impossible"
                elif any(k in text for k in ["more information", "need more", "clarify", "more details"]):
                    decision = "more_research"
                else:
                    decision = "pass"
                parsed = {"decision": decision, "reason": str(raw), "missing_information": []}

            state.setdefault("workflow_state", {})["validation_result"] = parsed
            state["workflow_state"]["validation_decision"] = parsed.get("decision", decision)
            state["workflow_state"]["validation_summary"] = parsed.get("reason", str(raw))
            state["workflow_state"]["validation_output"] = parsed

            print("VALIDATOR OUT")
            print(state["workflow_state"]["tool_results"].keys())
        except ModelInvocationError:
            raise
        except Exception as e:
            state.setdefault("workflow_state", {})["validation_result"] = {"decision": "more_research", "reason": str(e), "missing_information": []}
            state["workflow_state"]["validation_decision"] = "more_research"
            state["workflow_state"]["validation_output"] = state["workflow_state"]["validation_result"]

        return state

    def build(self):
        graph = StateGraph(AgentState)
        graph.add_node("intake", self.intake_node)
        graph.add_node("research", self.research_node)
        graph.add_node("intake_tool", self.tool_node)
        graph.add_node("research_tool", self.tool_node)
        graph.add_node("validator", self.validator_node)
        graph.add_node("writer", self.writer_node)

        graph.add_edge(START, "intake")
        graph.add_conditional_edges(
            "intake",
            self.route_after_intake,
            {
                "intake_tool": "intake_tool",
                "research": "research",
            },
        )
        graph.add_edge("intake_tool", "intake")
        graph.add_conditional_edges(
            "research",
            self.should_continue,
            {
                "research_tool": "research_tool",
                "validator": "validator",
                'writer': "writer",
                "end": END,
            },
        )
        graph.add_edge("research_tool", "research")
        graph.add_conditional_edges(
            "validator",
            self.route_after_validation,
            {
                "research": "research",
                "writer": "writer",
                "end": END,
            },
        )
        graph.add_edge("writer", END)

        return graph.compile()

class AgentRunner:
    def __init__(self, router):
        self.router = router
        self.graph_builder = GraphBuilder(router)
        self.app = self.graph_builder.build()
        self.summary_llm = load_summarizier_llm()
        self.fallback_json_llm = load_fallback_to_json_llm()

    def _validate_final_output(self, output: dict, trace: ExecutionTrace):
        workflow_state = output.get("workflow_state", {}) if isinstance(output, dict) else {}
        final_response = str(workflow_state.get("final_user_response") or "").strip()
        writer_output = str(workflow_state.get("writer_output") or "").strip()

        checks = {
            "planning_completed": bool(workflow_state.get("planning_output") or workflow_state.get("intake_result")),
            "research_completed": bool(workflow_state.get("research_output") or workflow_state.get("research_result")),
            "validation_completed": bool(workflow_state.get("validation_output") or workflow_state.get("validation_result")),
            "writer_completed": bool(writer_output),
            "final_matches_writer": bool(final_response and final_response == writer_output),
            "no_tool_artifacts": "<function=" not in final_response and "tool_calls" not in final_response,
        }
        trace.record("workflow_completion_checks", checks)
        if not all(checks.values()):
            raise RuntimeError(f"Workflow completion checks failed: {checks}")
        workflow_state["workflow_status"] = "completed"
        return final_response

    def run_agent(self, user_input, preference="", history="", memory="", user_id='', request_id: str = None, conversation_id: str = None, context_bundle: dict | None = None, user_tier: str = "Pirate"):
        trace = ExecutionTrace(request_id=request_id)
        trace.record("run_agent_start", {"user_input": user_input[:300], "user_id": user_id})
        t0 = time.time()
        
        config = {"configurable": {
            "thread_id": conversation_id or "default",
            "trace": trace
        }}

        try:
            output = None
            initial_data = {
                "messages": [HumanMessage(content=user_input)],
                "preference": preference,
                "history": history,
                "memory": memory,
                "context_bundle": context_bundle or {
                    "relevant_memory": memory,
                    "recent_messages_text": history,
                    "current_query": user_input,
                },
                "user_tier": user_tier,
                "user_id": user_id,
                "workflow_state": self.graph_builder._get_default_workflow_state(user_input)
            }


            if output is None:
                output = run_with_timeout(self.app, initial_data, config=config)
                output.setdefault("hitl_question", None)


            final_response = self._validate_final_output(output, trace)
            trace.record(
                "final_response",
                {"response_preview": final_response[:200]},
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
        return str(getattr(fallback, "content", "")).strip()

class TravelEngine:
    def __init__(self, agent_runner: AgentRunner):
        self.agent_runner = agent_runner

    def process_query(self, user_input, preference="", history="", memory="", user_id ="", conversation_id="", streaming_callback=None, context_bundle: dict | None = None, user_tier: str = "Pirate"):
        if not user_id:
            raise ValueError("user_id required")

        output = self.agent_runner.run_agent(
            user_input=user_input,
            preference=preference,
            history=history,
            memory=memory,
            user_id=user_id,
            request_id=conversation_id,
            conversation_id=conversation_id,
            context_bundle=context_bundle,
            user_tier=user_tier,
        )
        hitl_question = output.get("hitl_question") if isinstance(output, dict) else None
        if hitl_question:
            return hitl_question, "", history, True

        workflow_state = output.get("workflow_state", {})
        response = workflow_state.get("final_user_response")
        is_hitl = False

        content = self._parse_response(response)
        reply = self._extract_reply(content)

        convo = f"""user query: 
                {user_input} 
                agent reply: 
                {reply}"""

        if len(history) > 300:
            history = self._summarizier(history=history, user_message=convo)
        else:
            history += convo

        return reply, history, is_hitl

    def _parse_response(self, response):
        return response

    def _extract_reply(self, content):
        if isinstance(content, dict) and "reply" in content:
            return content["reply"]
        if isinstance(content, dict) and "message" in content:
            return content["message"]
        return str(content)

    def _summarizier(self, history, user_message):
        history = self.agent_runner.summary_agent(history, user_message)
        return history
