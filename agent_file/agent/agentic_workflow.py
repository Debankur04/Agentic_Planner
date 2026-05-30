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
from typing import Dict, Any
import time
import logging
from agent_file.agent.exceptions import NodeExecutionError, WorkflowExecutionError

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

def ensure_valid_node_output(result: Any, node_name: str) -> dict:
    if not isinstance(result, dict):
        raise NodeExecutionError(node_name, result)
    return result

def run_with_timeout(app, input_data, config):
    with concurrent.futures.ThreadPoolExecutor() as executor:
        future = executor.submit(app.invoke, input_data, config)
        try:
            return future.result(timeout=30)
        except concurrent.futures.TimeoutError:
            raise HTTPException(408, detail="Request timeout (30s)")


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
            """Ask the user a question to clarify one of these missing critical fields only: source city, budget, start date, or tenure."""
            return question

        self.intake_tools = [ask_human]
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
            get_code_station
        ]
        self.tools = self.research_tools + self.intake_tools
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

    # ------------------ SHARED LLM HELPERS ------------------
    def _get_last_user_message(self, state: MessagesState) -> str:
        messages = state.get("messages", [])
        if not messages:
            return ""
        return getattr(messages[-1], "content", "")

    def _get_original_user_request(self, state: MessagesState) -> str:
        if "workflow_state" in state and state["workflow_state"].get("user_input"):
            return state["workflow_state"]["user_input"]
        for msg in state.get("messages", []):
            if isinstance(msg, HumanMessage):
                return getattr(msg, "content", "")
        return self._get_last_user_message(state)

    def _invoke_llm(self, messages, state: MessagesState, config: dict, agent_name: str, tools):
        config = config or {}
        trace = config.get("configurable", {}).get("trace")
        user_id = state.get("user_id", "")
        if trace:
            trace.record(f"{agent_name}_start", {"message_count": len(messages), "user_id": user_id})

        if not token_tracker.check_budget(user_id, user_tier='free'):
            raise HTTPException(429, detail={
                "error": "daily_budget_exceeded",
                "message": "You've reached your daily AI usage limit. Upgrade to continue.",
                "reset_at": "midnight UTC"
            })

        attempted = set()
        while True:
            try:
                model_key = self.router.select_model(self._get_last_user_message(state), exclude_models=attempted)
            except RuntimeError:
                raise HTTPException(500, "All models exhausted")

            if model_key in attempted:
                raise HTTPException(500, "All models exhausted")

            if attempted and trace:
                trace.record("llm_retry", {
                    "retry_model": model_key,
                    "already_tried": list(attempted)
                })

            attempted.add(model_key)
            if trace:
                trace.record("model_selected", {
                    "model_key": model_key,
                    "model_name": self.router.config["models"][model_key]["model_name"],
                    "provider": self.router.config["models"][model_key]["provider"]
                })

            client = self.router.get_client(model_key)
            if trace:
                trace.record("client_initialized", {"model_key": model_key})

            llm = client.bind_tools(tools)
            if trace:
                trace.record("tools_bound", {
                    "model_key": model_key,
                    "tools": [t.name for t in tools]
                })

            if trace:
                trace.record("llm_invoke_start", {
                    "model_key": model_key,
                    "message_count": len(messages)
                })
            start = time.time()
            try:
                response = llm.invoke(messages)
                latency = (time.time() - start) * 1000
                self.router.record_success(model_key, latency)
                if trace:
                    trace.record("llm_invoke_success", {
                        "model": model_key,
                        "response_preview": str(getattr(response, "content", ""))[:200],
                        "has_tool_calls": bool(getattr(response, "tool_calls", None))
                    }, latency_ms=latency)
                break
            except Exception as e:
                self.router.record_failure(model_key, e)
                if trace:
                    trace.record("llm_invoke_error", {"model": model_key, "error": str(e)})

        model_name = self.router.config["models"][model_key]["model_name"]
        usage_data = getattr(response, "usage", None)
        if usage_data:
            usage = TokenUsage(
                input_tokens=usage_data.prompt_tokens,
                output_tokens=usage_data.completion_tokens,
                model=model_name
            )
            token_tracker.record_usage(user_id, usage)

        return response

    def _append_state_response(self, state: MessagesState, response, agent_name: str):
        state["workflow_state"]["current_agent"] = agent_name
        state["workflow_state"]["last_response_preview"] = str(getattr(response, "content", ""))[:1000]
        return {"messages": state["messages"] + [response]}

    def _parse_decision_from_text(self, text: str) -> str:
        normalized = text.lower()
        if any(keyword in normalized for keyword in ["impossible", "cannot", "no feasible", "not possible", "unavailable"]):
            return "impossible"
        if any(keyword in normalized for keyword in ["more information", "need more", "clarify", "clarification", "more details"]):
            return "more_research"
        return "pass"

    # ------------------ INTAKE AGENT NODE ------------------
    def intake_node(self, state: MessagesState, config: dict = None):
        config = config or {}
        trace = config.get("configurable", {}).get("trace")
        messages = state.get("messages", [])
        original_request = self._get_original_user_request(state)
        user_input = original_request

        if "workflow_state" not in state:
            state["workflow_state"] = self._get_default_workflow_state(user_input=original_request)
        state["workflow_state"]["user_input"] = original_request
        state["workflow_state"]["phase"] = "intake"
        state["workflow_state"]["current_agent"] = "intake"

        asked_questions = state["workflow_state"].get("clarification_questions", [])
        previous_clarification_history = self._format_clarification_history(state)
        last_question = state["workflow_state"].get("last_clarification_question", "none")
        clarification_answer_text = self._get_clarification_answer(state)

        system_prompt = (
            "You are the intake agent for a travel planning workflow. "
            "Your job is to decide whether the user request is complete enough to start research, "
            "or whether you need to ask the user for more information. "
            "Use ask_human only for these missing critical values: source city, budget, start date, or tenure. "
            "Do not ask for end date, destination, accommodation, route details, or any other field. "
            "If the user has already answered a clarification, do not ask the same or a similar question again. "
            "Treat the previous clarification answer as final unless a different allowed field is missing. "
            "If the core fields source city, destination, budget, start date, and tenure are already present, do not ask anything. "
            "If other travel details are missing, assume moderate defaults in a reasonable way without asking. "
            "Do not ask more than one clarification question in this intake pass. "
            "If the destination is missing, infer a sensible option rather than asking about it."
        )
        user_prompt = (
            f"User request: {original_request}\n"
            f"Previous clarification history:\n{previous_clarification_history}\n"
            f"Last clarification question: {last_question}\n"
            f"Clarification answer: {clarification_answer_text}\n"
            "Provide a structured intake plan with assumed defaults for missing details. "
            "Only call ask_human for source city, budget, start date, or tenure. "
            "IMPORTANT: The field 'clarification_answer' contains the user's answer to a previous question. "
            "If clarification_answer is non-empty, treat it as final and DO NOT call ask_human again. "
            "Proceed directly to producing the intake plan."
        )
        prompt_messages = [SystemMessage(content=system_prompt), HumanMessage(content=user_prompt)]

        response = self._invoke_llm(prompt_messages, state, config, agent_name="intake", tools=self.intake_tools)
        state["workflow_state"]["intake_result"] = {"raw_output": str(getattr(response, "content", ""))}
        if hasattr(response, "tool_calls") and response.tool_calls:
            state["workflow_state"]["intake_result"]["tool_calls"] = [tc["name"] for tc in response.tool_calls]

        return self._append_state_response(state, response, agent_name="intake")

    # ------------------ RESEARCH AGENT NODE ------------------
    def research_node(self, state: MessagesState, config: dict = None):
        config = config or {}
        trace = config.get("configurable", {}).get("trace")
        state.setdefault("workflow_state", self._get_default_workflow_state(user_input=self._get_last_user_message(state)))
        state["workflow_state"]["phase"] = "research"
        state["workflow_state"]["current_agent"] = "research"

        user_input = state["workflow_state"].get("user_input", self._get_original_user_request(state))
        clarification_answer = state["workflow_state"].get("clarification_answer", self._get_clarification_answer(state))
        intake_output = state["workflow_state"].get("intake_result", {}).get("raw_output", "")
        if clarification_answer:
            intake_output += f"\nClarification answer: {clarification_answer}"

        system_prompt = (
            "You are the research agent. Use all available travel tools to gather routes, pricing, weather, and availability. "
            "Do not ask the user any additional questions. "
            "Only investigate feasible travel connections and clearly explain any impossible or non-viable routes. "
            "If no viable rail or land route exists, state that directly and focus on the practical alternative. "
            "Assume reasonable defaults for any missing details outside the allowed clarification fields, including destination, accommodation, and trip length. "
            "Do not use ask_human or request more user input."
        )
        user_prompt = (
            f"User request: {user_input}\n"
            f"Intake plan: {intake_output}\n"
            "Use tools when appropriate to collect journey data, route options, fees, and weather information. "
            "If you can resolve the journey with the information available, do so. "
            "If a requested route is impossible, explain why and identify realistic alternatives."
        )
        prompt_messages = [SystemMessage(content=system_prompt), HumanMessage(content=user_prompt)]

        response = self._invoke_llm(prompt_messages, state, config, agent_name="research", tools=self.research_tools)
        state["workflow_state"]["research_result"] = {"raw_output": str(getattr(response, "content", ""))}
        if hasattr(response, "tool_calls") and response.tool_calls:
            state["workflow_state"]["research_result"]["tool_calls"] = [tc["name"] for tc in response.tool_calls]

        return self._append_state_response(state, response, agent_name="research")

    # ------------------ RESEARCH VALIDATION NODE ------------------
    def validation_node(self, state, config=None):
        # Get research_result stored in workflow_state — don't rely on message scan
        research_text = state.get("workflow_state", {}).get("research_result", {}).get("raw_output", "")
        
        if not research_text:
            # fallback: scan messages
            for msg in reversed(state["messages"]):
                if not isinstance(msg, ToolMessage) and hasattr(msg, "content") and msg.content:
                    research_text = str(msg.content)
                    break
        
        decision = self._parse_decision_from_text(research_text)
        state["workflow_state"]["validation_decision"] = decision
        state["workflow_state"]["validation_summary"] = research_text  # ✅ no truncation
        return {"messages": state["messages"]}

    # ------------------ WRITER AGENT NODE ------------------
    def writer_node(self, state: MessagesState, config: dict = None):
        config = config or {}
        state.setdefault("workflow_state", self._get_default_workflow_state(user_input=self._get_last_user_message(state)))
        state["workflow_state"]["phase"] = "writer"
        state["workflow_state"]["current_agent"] = "writer"

        user_input = state["workflow_state"].get("user_input", "")
        research_text = state["workflow_state"].get("research_result", {}).get("raw_output", "")

        system_prompt = (
            "You are a travel writer. Create a polished, user-friendly travel summary and recommendation based on the research output. "
            "Do not invent facts. If the journey is impossible, explain why clearly. "
            "If assumptions were required, state them clearly as assumptions. "
            "If the user already provided source city, destination, budget, start date, and tenure, do not suggest that no details were given. "
            "Only mention assumptions for details that were actually missing and necessary to complete the plan."
        )
        user_prompt = (
            f"User request: {user_input}\n"
            f"Research findings: {research_text}\n"
            "Write the final response as a helpful travel plan or recommendation. "
            "Mention any assumed defaults only when they were necessary and label them explicitly as assumptions."
        )
        prompt_messages = [SystemMessage(content=system_prompt), HumanMessage(content=user_prompt)]

        response = self._invoke_llm(prompt_messages, state, config, agent_name="writer", tools=[])
        state["workflow_state"]["final_output"] = str(getattr(response, "content", ""))

        return self._append_state_response(state, response, agent_name="writer")

    # ------------------ TOOL NODE ------------------
    def tool_node(self, state: MessagesState, config: dict = None):
        config = config or {}
        last_message = state["messages"][-1]
        trace = config.get("configurable", {}).get("trace")
        outputs = []
        if "workflow_state" not in state:
            state["workflow_state"] = self._get_default_workflow_state(user_input="")
        current_agent = state["workflow_state"].get("current_agent", "research")
        state["workflow_state"]["current_agent"] = "tool"

        if hasattr(last_message, "tool_calls") and last_message.tool_calls:
            for tool_call in last_message.tool_calls:
                tool_name = tool_call["name"]
                args = tool_call["args"]
                print(f"\n🔥 EXECUTING TOOL: {tool_name}")
                print(f"📦 ARGS: {args}")
                if trace:
                    trace.record("tool_called", {"tool": tool_name, "args": str(args)[:300]})
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
                            if trace:
                                trace.record("tool_success", {"tool": tool_name, "result_preview": str(result)[:200]}, latency_ms=t1)
                            if tool_name == "ask_human":
                                question_text = args.get("question") if isinstance(args, dict) else str(args)
                                normalized = question_text.lower()
                                allowed_terms = [
                                    "source city",
                                    "origin city",
                                    "departure city",
                                    "departure location",
                                    "budget",
                                    "start date",
                                    "departure date",
                                    "tenure",
                                    "trip length",
                                    "length of stay"
                                ]
                                if not any(term in normalized for term in allowed_terms):
                                    result = (
                                        "Clarification blocked: only ask about source city, budget, start date, or tenure. "
                                        "Assume other missing details moderately and continue."
                                    )
                                    state["workflow_state"]["ask_human_blocked"] = True
                                else:
                                    state["workflow_state"]["ask_human_blocked"] = False
                                    self._record_clarification_question(state, question_text)
                                    state["workflow_state"]["clarification_answer"] = ""
                                if isinstance(result, dict) and "error" in result:
                                    result = "Tool failed. Continue with available data."
                                else:
                                    set_cache(cache_key, result, ttl=300)
                            else:
                                if isinstance(result, dict) and "error" in result:
                                    result = "Tool failed. Continue with available data."
                                else:
                                    set_cache(cache_key, result, ttl=300)
                        except Exception as e:
                            result = f"Tool error: {str(e)}"
                            if trace:
                                trace.record("tool_error", {"tool": tool_name, "error": str(e)})
                            state["workflow_state"]["tool_results"][tool_name] = {"error": str(e)}
                    else:
                        result = "Tool not found"
                print(f"✅ RESULT: {result}")
                outputs.append(ToolMessage(content=str(result), tool_call_id=tool_call["id"]))

        state["workflow_state"]["current_agent"] = current_agent
        return {"messages": state["messages"] + outputs}

    # ------------------ ASK HUMAN NODE ------------------
    def ask_human_node(self, state: MessagesState):
        state.setdefault("workflow_state", self._get_default_workflow_state(user_input=self._get_last_user_message(state)))
        state["workflow_state"]["current_agent"] = "ask_human"

        clarification_question = None
        clarification_question_index = None
        for index, msg in enumerate(state["messages"]):
            if not isinstance(msg, ToolMessage) and hasattr(msg, "tool_calls") and msg.tool_calls:
                for tc in msg.tool_calls:
                    if tc["name"] == "ask_human":
                        clarification_question = tc["args"].get("question") if isinstance(tc["args"], dict) else str(tc["args"])
                        clarification_question_index = index
                        break
                if clarification_question:
                    break

        if clarification_question:
            self._record_clarification_question(state, clarification_question)

            clarification_answer = None
            for msg in state["messages"][clarification_question_index + 1:]:
                if isinstance(msg, HumanMessage):
                    content = getattr(msg, "content", "").strip()
                    if content:
                        clarification_answer = content
                        break

            if clarification_answer:
                self._record_clarification_answer(state, clarification_question, clarification_answer)

        return {"messages": state["messages"]}

    # ------------------ ROUTING ------------------
    def route_after_intake(self, state: MessagesState):
        last_message = state["messages"][-1]
        if state.get("workflow_state", {}).get("ask_human_blocked"):
            return "research"
        if hasattr(last_message, "tool_calls") and any(tc["name"] == "ask_human" for tc in last_message.tool_calls):
            return "ask_human_node"
        return "research"

    def route_after_tool(self, state: MessagesState):
        current_agent = state.get("workflow_state", {}).get("current_agent", "research")
        if current_agent == "intake":
            return "intake"
        if current_agent == "research":
            return "research"
        if current_agent in {"writer", "writer_impossible"}:
            return current_agent
        return "research"

    def route_after_validation(self, state: MessagesState):
        decision = state.get("workflow_state", {}).get("validation_decision", "pass")
        if decision == "more_research":
            return "research"
        if decision == "impossible":
            return "writer_impossible"
        return "writer"

    def should_continue(self, state: MessagesState):
        messages = state["messages"]
        last_message = messages[-1]
        if not hasattr(last_message, "tool_calls") or not last_message.tool_calls:
            return "validate"
        if any(tc["name"] == "ask_human" for tc in last_message.tool_calls):
            return "ask_human_node"
        if len(messages) > 15:
            return "end"
        
        # ✅ Compare tool NAMES called across AI messages, not tool result content
        all_tool_calls = []
        for m in messages:
            if hasattr(m, "tool_calls") and m.tool_calls:
                for tc in m.tool_calls:
                    all_tool_calls.append(tc["name"])
        if len(all_tool_calls) != len(set(all_tool_calls)):
            print("⚠️ Repeated tool call detected. Stopping loop.")
            return "end"
        return "tool"

    # ------------------ BUILD GRAPH ------------------
    def build(self):
        graph = StateGraph(MessagesState)
        graph.add_node("intake", self.intake_node)
        graph.add_node("research", self.research_node)
        graph.add_node("validation", self.validation_node)
        graph.add_node("writer", self.writer_node)
        graph.add_node("writer_impossible", self.writer_impossible_node)
        graph.add_node("tool", self.tool_node)
        graph.add_node("ask_human_node", self.ask_human_node)

        graph.add_edge(START, "intake")
        graph.add_conditional_edges(
            "intake",
            self.route_after_intake,
            {
                "ask_human_node": "ask_human_node",
                "research": "research",
                "end": END
            }
        )
        graph.add_edge("ask_human_node", "intake")
        graph.add_conditional_edges(
            "research",
            self.should_continue,
            {
                "tool": "tool",
                "ask_human_node": "ask_human_node",
                "validate": "validation",
                "end": END
            }
        )
        graph.add_conditional_edges(
            "tool",
            self.route_after_tool,
            {
                "intake": "intake",
                "research": "research",
                "writer": "writer",
                "writer_impossible": "writer_impossible",
                "end": END
            }
        )
        graph.add_conditional_edges(
            "validation",
            self.route_after_validation,
            {
                "research": "research",
                "writer": "writer",
                "writer_impossible": "writer_impossible"
            }
        )

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

        if not isinstance(output, dict) or "messages" not in output:
            raise WorkflowExecutionError("LLM agent run returned invalid output", details={"output": output})

        response = None
        is_hitl = False
        for msg in reversed(output["messages"]):
            if not isinstance(msg, ToolMessage):
                response = msg.content
                if hasattr(msg, "additional_kwargs") and msg.additional_kwargs.get("is_hitl"):
                    is_hitl = True
                if not response and hasattr(msg, "tool_calls") and msg.tool_calls:
                    response = "I've explored multiple options but couldn't finalize a complete itinerary within the search limit. Could you please provide more specific preferences (like exact dates or transport modes) so I can narrow down the search?"
                break

        if is_hitl:
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

        if isinstance(content, dict) and content.get("confidence", 0) >= 80:
            return content.get("preference")
        return None

    def _summarizier(self, history, user_message):
        history = self.agent_runner.summary_agent(history, user_message)
        return history