from langchain_core.messages import SystemMessage, ToolMessage, HumanMessage
import json
from langgraph.graph import StateGraph, MessagesState, END, START

from agent_file.utils.model_loader import load_llm, load_summarizier_llm
from agent_file.prompt_library.prompt import SYSTEM_PROMPT
from agent_file.prompt_library.prompt_maker import *

# ✅ Tools
from agent_file.tools.flight_search import get_flight_search_tool
from agent_file.tools.hotel_search import get_hotel_search_tool
from agent_file.tools.place_search_tool import get_place_search_tools
from agent_file.tools.weather_info_tool import get_weather_tools


class GraphBuilder:
    def __init__(self):
        self.llm = load_llm()

        search_attractions, search_restaurants, search_activities, search_transportation = get_place_search_tools()
        find_flights = get_flight_search_tool()
        search_hotel = get_hotel_search_tool()
        get_current_weather, get_weather_forecast = get_weather_tools()

        self.tools = [
            find_flights,
            search_hotel,
            search_attractions,
            search_restaurants,
            search_activities,
            search_transportation,
            get_current_weather,
            get_weather_forecast
        ]

        self.llm_with_tools = self.llm.bind_tools(self.tools)
        self.system_prompt = SYSTEM_PROMPT
        self.tool_map = {tool.name: tool for tool in self.tools}

    # ------------------ AGENT NODE ------------------
    def agent_function(self, state: MessagesState):
        messages = state["messages"]  # ✅ FIX: preserve full history

        user_message = messages[-1].content
        preference = state.get("preference", "")
        history = state.get("history", "")
        memory = state.get("memory", "")

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

        response = self.llm_with_tools.invoke(messages)

        print("\n🧠 LLM RESPONSE:", response)
        print("🛠 TOOL CALLS:", getattr(response, "tool_calls", None))

        return {
            "messages": state["messages"] + [response]
        }

    # ------------------ TOOL NODE ------------------
    def tool_node(self, state: MessagesState):
        last_message = state["messages"][-1]
        outputs = []

        if hasattr(last_message, "tool_calls") and last_message.tool_calls:
            for tool_call in last_message.tool_calls:
                tool_name = tool_call["name"]
                args = tool_call["args"]

                print(f"\n🔥 EXECUTING TOOL: {tool_name}")
                print(f"📦 ARGS: {args}")

                if tool_name in self.tool_map:
                    try:
                        result = self.tool_map[tool_name].invoke(args)

                        # ✅ FIX: handle API errors properly
                        if isinstance(result, dict) and "error" in result:
                            result = "Tool failed. Continue with available data."

                    except Exception as e:
                        result = f"Tool error: {str(e)}"
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

    # ------------------ ROUTING ------------------
    def should_continue(self, state: MessagesState):
        messages = state["messages"]
        last_message = messages[-1]

        # ✅ STOP if no tool calls
        if not hasattr(last_message, "tool_calls") or not last_message.tool_calls:
            return "end"

        # ✅ STOP infinite loops (max steps)
        if len(messages) > 8:
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

        graph.add_edge(START, "agent")

        graph.add_conditional_edges(
            "agent",
            self.should_continue,
            {
                "tool": "tool",
                "end": END
            }
        )

        graph.add_edge("tool", "agent")

        return graph.compile()


class AgentRunner:
    def __init__(self):
        agent = GraphBuilder()
        self.app = agent.build()
        self.summary_llm = load_summarizier_llm()

    def run_agent(self, user_input, preference="", history="", memory=""):
        output = self.app.invoke({
            "messages": [HumanMessage(content=user_input)],
            "preference": preference,
            "history": history,
            "memory": memory
        })
        return output

    def summary_agent(self, history: str, user_message: str):
        prompt = summarize_history(history=history, user_message=user_message)
        new_history = self.summary_llm.invoke(prompt)
        return new_history.content.strip()


class TravelEngine:
    def __init__(self, agent_runner):
        self.agent_runner = agent_runner

    def process_query(self, user_input, preference="", history="", memory=""):
        output = self.agent_runner.run_agent(user_input, preference, history, memory)

        # ✅ FIX: get last AI message (not tool message)
        response = None
        for msg in reversed(output["messages"]):
            if not isinstance(msg, ToolMessage):
                response = msg.content
                break

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

        return reply, pref, history

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