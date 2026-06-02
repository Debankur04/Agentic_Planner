from langchain_core.messages import SystemMessage, ToolMessage, HumanMessage
import json
from langgraph.graph import StateGraph, MessagesState, END, START, add_messages
from langgraph.checkpoint.memory import MemorySaver
from langchain_core.tools import tool
from langchain_core.messages import AIMessage
from llmops.token_tracker import *
from agent_file.utils.model_loader import *
from agent_file.prompt_library.prompt_maker import *
from fastapi import HTTPException
from typing import Dict, Any, Annotated, TypedDict
import time
import logging
from agent_file.prompt_library.multi_agent_prompts import build_intake_prompt, build_research_prompt, build_writer_prompt

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

logger = logging.getLogger(__name__)
token_tracker = TokenTracker(redis_client=redis_client)


# @tool
# def ask_human(question: str) -> str:
#     """Ask the user a question to clarify one of these missing critical fields only: source city, budget, start date, or tenure."""
#     return question

def merge_dicts(left: dict, right: dict) -> dict:
    return {**left, **right}

import contextvars

def run_with_timeout(app, input_data, config):
    ctx = contextvars.copy_context()
    with concurrent.futures.ThreadPoolExecutor() as executor:
        future = executor.submit(ctx.run, app.invoke, input_data, config)
        try:
            return future.result(timeout=30)
        except concurrent.futures.TimeoutError:
            raise HTTPException(408, detail="Request timeout (30s)")


class AgentState(TypedDict):
    messages: Annotated[list, add_messages]
    workflow_state: Annotated[dict, merge_dicts]
    user_id: str
    preference: str
    history: str
    memory: str

    # Optional values may be added by workflow nodes
    # such as thread ids, tool results, and state metadata.

    # NOTE: langgraph requires a typed state schema for compile-time validation.


class GraphBuilder:
    def __init__(self, router):
        self.router = router

        search_attractions, search_restaurants, search_activities, search_transportation = get_place_search_tools()
        find_flights = get_flight_search_tool()
        search_hotel = get_hotel_search_tool()
        get_current_weather, get_weather_forecast = get_weather_tools()
        find_routes, estimate_delay, live_train_update, get_schedule, get_code_station = get_railway_search_tool()

        # self.intake_tools = [ask_human]
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
        }

    def _append_state_response(self, state, response, agent_name):
        # Append the agent response to the existing messages list
        existing = state.get("messages", []) or []
        return {
            **state,
            "messages": existing + [response],
        }

    def _invoke_llm(self, prompt_messages: list, state: MessagesState, config: dict, agent_name: str, tools: list):
        print("STATE TYPES")
        for k, v in state.items():
            print(k, type(v))

        print("CONFIG TYPES")
        for k, v in config.items():
            print(k, type(v))
        try:
            llm = self.router.get_llm(agent_name)
        except Exception as e:
            print(f"[GraphBuilder] ERROR selecting llm for agent={agent_name}: {e}")
            raise

        tool_names = [getattr(tool, "name", str(tool)) for tool in tools]
        print(f"[GraphBuilder] invoking llm {agent_name} using {llm} with tools={tool_names}")
        llm = llm.bind_tools(tools)

        return llm.invoke(prompt_messages)

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
        history = state.get("history", "")
        memory = state.get("memory", "")
        
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
        if hasattr(response, "tool_calls") and response.tool_calls:
            state["workflow_state"]["intake_tool_calls"] = [tc["name"] for tc in response.tool_calls]

        return self._append_state_response(state, response, agent_name="intake")

    def research_node(self, state: AgentState, config: dict = None):
        print("RESEARCH STATE")
        print(state)
        print("KEYS:", state.keys())
        config = config or {}
        state["workflow_state"]["phase"] = "research"
        self._log_node_entry("research", state)

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
            history=state.get("history", ""),
            memory=state.get("memory", ""),
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
        state["workflow_state"]["validation_summary"] = research_text
        # Record any tool calls suggested by the research agent
        if hasattr(response, "tool_calls") and response.tool_calls:
            state["workflow_state"]["research_tool_calls"] = [tc["name"] for tc in response.tool_calls]

        return self._append_state_response(state, response, agent_name="research")

    def writer_node(self, state: AgentState, config: dict = None):
        print("WRITER INPUT")
        print(state["workflow_state"]["tool_results"])
        print(state["workflow_state"]["research_result"])
        print(state["history"])
        config = config or {}
        state["workflow_state"]["phase"] = "writer"
        self._log_node_entry("writer", state)

        user_input = state["workflow_state"].get("user_input", "")
        validated_summary = (
    state["workflow_state"].get("validation_summary")
    or state["workflow_state"].get("research_result", "")
)
        print("="*50)
        print("USER INPUT")
        print(user_input)

        print("="*50)
        print("VALIDATED SUMMARY")
        print(validated_summary)

        print("="*50)
        print("TOOL RESULTS")
        print(state["workflow_state"].get("tool_results"))
        system_prompt, user_prompt = build_writer_prompt(
            user_input,
            validated_summary,
            tool_results=state["workflow_state"].get("tool_results", {}),
            preference=...,
            relevant_memory=...
        )
        prompt_messages = [SystemMessage(content=system_prompt), HumanMessage(content=user_prompt)]

        response = self._invoke_llm(prompt_messages, state, config, agent_name="writer", tools=[])
        state["workflow_state"]["final_output"] = getattr(response, "content", "")

        return self._append_state_response(state, response, agent_name="writer")

    def tool_node(self, state: MessagesState, config: dict = None):
        config = config or {}
        trace = config.get("configurable", {}).get("trace")
        outputs = []

        last_message = state["messages"][-1]
        # ask_human tool is disabled in this test flow.
        # ask_human_call = None
        # if hasattr(last_message, "tool_calls") and last_message.tool_calls:
        #     ask_human_call = next((tc for tc in last_message.tool_calls if tc["name"] == "ask_human"), None)

        # if ask_human_call is not None:
        #     return {
        #         "messages": state["messages"],
        #         "workflow_state": state["workflow_state"],
        #     }

        # if isinstance(last_message, HumanMessage) and len(state["messages"]) > 1:
        #     previous_message = state["messages"][-2]
        #     if hasattr(previous_message, "tool_calls") and previous_message.tool_calls:
        #         ask_human_call = next((tc for tc in previous_message.tool_calls if tc["name"] == "ask_human"), None)
        #         if ask_human_call is not None:
        #             question_text = ask_human_call["args"].get("question") if isinstance(ask_human_call["args"], dict) else str(ask_human_call["args"])
        #             answer_text = getattr(last_message, "content", "").strip()
        #             if answer_text:
        #                 clarification_history = state["workflow_state"].setdefault("clarification_history", {})
        #                 clarification_history[question_text] = answer_text
        #                 state["workflow_state"]["clarification_answer"] = answer_text
        #                 state["workflow_state"]["last_clarification_question"] = question_text
        #                 state["workflow_state"]["ask_human_blocked"] = False

        last_message = state["messages"][-1]
        if hasattr(last_message, "tool_calls") and last_message.tool_calls:
            for tool_call in last_message.tool_calls:
                if tool_call["name"] == "ask_human":
                    continue
                tool_name = tool_call["name"]
                args = tool_call.get("args")
                # If we already have results for this tool, reuse them instead of re-calling
                existing = state.get("workflow_state", {}).get("tool_results", {}).get(tool_name)
                if existing is not None:
                    logger.debug("Using cached tool result for %s", tool_name)
                    outputs.append(ToolMessage(content=str(existing), tool_call_id=tool_call.get("id")))
                    continue

                logger.debug("Executing tool %s with args=%s", tool_name, args)
                if trace:
                    trace.record("tool_called", {"tool": tool_name, "args": str(args)[:300]})
                result = self._execute_tool(state, tool_call, trace)
                logger.debug("Tool %s result: %s", tool_name, result)
                outputs.append(ToolMessage(content=str(result), tool_call_id=tool_call["id"]))

        # Return the full state with messages extended by tool outputs and
        # preserve workflow_state so reducers/mergers keep other keys.
        return {**state, "messages": state.get("messages", []) + outputs, "workflow_state": state.get("workflow_state", {})}

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

        if len(messages) > 15:
            print("ROUTE = end")
            return "end"

        all_tool_signatures = []
        for m in messages:
            if hasattr(m, "tool_calls") and m.tool_calls:
                for tc in m.tool_calls:
                    all_tool_signatures.append(self._tool_call_signature(tc))

        if len(all_tool_signatures) != len(set(all_tool_signatures)):
            print("ROUTE = writer")
            logger.warning("Repeated tool call detected. Stopping loop.")
            return "writer"

        print("ROUTE = research_tool")
        return "research_tool"

    def route_after_validation(self, state: AgentState):
        decision = state.get("workflow_state", {}).get("validation_decision", "pass")
        if decision == "more_research":
            return "research"
        if decision == "impossible":
            return "end"
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

            print("VALIDATOR OUT")
            print(state["workflow_state"]["tool_results"].keys())
        except Exception as e:
            state.setdefault("workflow_state", {})["validation_result"] = {"decision": "more_research", "reason": str(e), "missing_information": []}
            state["workflow_state"]["validation_decision"] = "more_research"

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

        self.checkpointer = MemorySaver()
        return graph.compile(checkpointer=self.checkpointer, interrupt_before=["research_tool"])

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
            output = None
            initial_data = {
                "messages": [HumanMessage(content=user_input)],
                "preference": preference,
                "history": history,
                "memory": memory,
                "user_id": user_id,
                "workflow_state": {
                    "user_input": user_input,
                    "tool_results": {},
                    "clarification_history": {},
                    "ask_human_blocked": False,
                    "phase": ""
                }
            }

            if state and state.next and any(node in state.next for node in ["intake_tool", "research_tool"]):
                # ask_human HITL path disabled for this test.
                pass

            if output is None:
                output = run_with_timeout(self.app, initial_data, config=config)
                output.setdefault("hitl_question", None)

            while True:
                state = self.app.get_state(config)
                if not state or not state.next:
                    break
                if any(node in state.next for node in ["intake_tool", "research_tool"]):
                    # ask_human HITL path disabled for this test.
                    output = run_with_timeout(self.app, None, config=config)
                    continue
                break

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
        return str(getattr(fallback, "content", "")).strip()

class TravelEngine:
    def __init__(self, agent_runner: AgentRunner):
        self.agent_runner = agent_runner

    def process_query(self, user_input, preference="", history="", memory="", user_id ="", conversation_id="", streaming_callback=None):
        if not user_id:
            raise ValueError("user_id required")

        output = self.agent_runner.run_agent(
            user_input=user_input,
            preference=preference,
            history=history,
            memory=memory,
            user_id=user_id,
            request_id=conversation_id,
            conversation_id=conversation_id
        )
        hitl_question = output.get("hitl_question") if isinstance(output, dict) else None
        if hitl_question:
            return hitl_question, "", history, True

        response = None
        is_hitl = False
        for msg in reversed(output["messages"]):
            if isinstance(msg, ToolMessage):
                continue

            if isinstance(msg, AIMessage) and msg.tool_calls:
                continue

            response = msg.content

            if hasattr(msg, "additional_kwargs") and msg.additional_kwargs.get("is_hitl"):
                is_hitl = True

            print('ping !!')
            break

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
        # Previously we attempted to auto-parse JSON here. Keep the response as-is
        # since LLMs will emit JSON when required and downstream consumers
        # can handle string or dict accordingly.
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