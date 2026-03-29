from langchain_core.messages import SystemMessage, ToolMessage, HumanMessage
import json
from langgraph.graph import StateGraph, MessagesState, END, START

from agent_file.utils.model_loader import load_llm, load_summarizier_llm
from agent_file.prompt_library.prompt import SYSTEM_PROMPT
from agent_file.prompt_library.prompt_maker import summarize_history

# ✅ Import tools correctly
from agent_file.tools.flight_search import get_flight_search_tool
from agent_file.tools.hotel_search import get_hotel_search_tool
from agent_file.tools.place_search_tool import get_place_search_tools
from agent_file.tools.weather_info_tool import get_weather_tools


class GraphBuilder:
    def __init__(self):
        self.llm = load_llm()

        # ✅ Load tools properly
        search_attractions, search_restaurants, search_activities, search_transportation = get_place_search_tools()
        find_flights = get_flight_search_tool()
        search_hotel = get_hotel_search_tool()
        get_current_weather, get_weather_forecast = get_weather_tools()

        # ✅ Tool list
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

        # ✅ Bind tools to LLM
        self.llm_with_tools = self.llm.bind_tools(self.tools)

        self.system_prompt = SYSTEM_PROMPT

        # ✅ Tool map for execution
        self.tool_map = {tool.name: tool for tool in self.tools}

    # ------------------ AGENT NODE ------------------
    def agent_function(self, state: MessagesState):
        messages = state["messages"]

        # Inject system prompt
        messages = [self.system_prompt] + messages

        response = self.llm_with_tools.invoke(messages)

        # 🔍 DEBUG
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
                    except Exception as e:
                        result = {"error": str(e)}
                else:
                    result = {"error": f"Tool '{tool_name}' not found"}

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
        last_message = state["messages"][-1]

        if hasattr(last_message, "tool_calls") and last_message.tool_calls:
            return "tool"

        return "end"

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

    def run_agent(self, user_input, preference="", history=""):
        output = self.app.invoke({
            "messages": [HumanMessage(content=user_input)],
            "preference": preference,
            "history": history
        })
        return output
    
    def summary_agent(self, history: str, user_message: str):
        prompt = summarize_history(history= history, user_message= user_message)
        new_history = self.summary_llm.invoke(prompt)
        return new_history.content.strip()
    

class TravelEngine:
    def __init__(self, agent_runner):
        self.agent_runner = agent_runner

    def process_query(self, user_input, preference="", history=""):
        output = self.agent_runner.run_agent(user_input, preference, history)

        response = output["messages"][-1].content

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
    
    def _summarizier(self,history, user_message):
        history = self.agent_runner.summary_agent(history,user_message)
        return history