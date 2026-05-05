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
import time

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
        find_routes, estimate_delay,live_train_update, get_schedule, get_code_station = get_railway_search_tool()

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
        self.system_prompt = SYSTEM_PROMPT
        self.tool_map = {tool.name: tool for tool in self.tools}

    # ------------------ AGENT NODE ------------------
    def agent_function(self, state: MessagesState, config: dict = None):
        config = config or {}
        messages = state["messages"]  # ✅ FIX: preserve full history

        user_message = messages[-1].content
        preference = state.get("preference", "")
        history = state.get("history", "")
        memory = state.get("memory", "")
        user_id = state.get("user_id", "")
        trace = config.get("configurable", {}).get("trace")
        streaming_callback = config.get("configurable", {}).get("streaming_callback")

        if trace:
            trace.record("agent_node_start", {"model_selection": "pending"})

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
                
                invoke_kwargs = {}
                if streaming_callback:
                    invoke_kwargs["config"] = {"callbacks": [streaming_callback]}
                    
                response = llm.invoke(messages, **invoke_kwargs)
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

        return {
            "messages": state["messages"] + [response]
        }

    # ------------------ TOOL NODE ------------------
    def tool_node(self, state: MessagesState, config: dict = None):
        config = config or {}
        last_message = state["messages"][-1]
        trace = config.get("configurable", {}).get("trace")
        outputs = []
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
                    else:
                        result = "Tool not found"

                print(f"✅ RESULT: {result}")

                outputs.append(
                    ToolMessage(
                        content=str(result),
                        tool_call_id=tool_call["id"]
                    )
                )

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

        # ✅ STOP if no tool calls
        if not hasattr(last_message, "tool_calls") or not last_message.tool_calls:
            return "end"

        # Route to ask_human_node if ask_human was called
        if any(tc["name"] == "ask_human" for tc in last_message.tool_calls):
            return "ask_human_node"

        # ✅ STOP infinite loops (max steps)
        if len(messages) > 15:
            print("⚠️ Max steps reached. Stopping loop.")
            return "end"

        # ✅ STOP repeated same tool calls
        tool_calls = [
            m for m in messages if isinstance(m, ToolMessage)
        ]
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



    def run_agent(self, user_input, preference="", history="", memory="", user_id='', request_id: str = None, streaming_callback=None, conversation_id: str = None):
        trace = ExecutionTrace(request_id=request_id)
        trace.record("run_agent_start", {"user_input": user_input[:300], "user_id": user_id})
        t0 = time.time()
        
        config = {"configurable": {
            "thread_id": conversation_id or "default",
            "trace": trace,
            "streaming_callback": streaming_callback
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
                
                # Stream the question directly to the frontend immediately
                if streaming_callback and hasattr(streaming_callback, 'on_llm_new_token'):
                    streaming_callback.on_llm_new_token(question)
                    
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

    def process_query(self, user_input, preference="", history="", memory="", user_id ="", streaming_callback=None, conversation_id=""):
        if not user_id:
            raise ValueError("user_id required")
        output = self.agent_runner.run_agent(user_input, preference, history, memory, user_id, streaming_callback=streaming_callback, conversation_id=conversation_id)

        # ✅ FIX: get last AI message (not tool message)
        response = None
        is_hitl = False
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