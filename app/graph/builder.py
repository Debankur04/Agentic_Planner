import asyncio
import time
from langgraph.graph import StateGraph, MessagesState, START, END
from langgraph.checkpoint.memory import MemorySaver
from app.schemas.state import PlannerState
from app.agents.intake import intake_node
from app.agents.planner import planner_node
from app.agents.research import research_node
from app.agents.synthesizer import synthesis_node
from app.agents.writer import writer_node
from app.validators.intake import validate_intake
from app.services.trace import TraceCollector
from app.services.json_recovery import safe_parse_json

class TravelPlannerGraph:
    def __init__(self):
        self.graph = self._build_graph()
        self.trace = TraceCollector()

    def _build_graph(self):
        graph = StateGraph(MessagesState)

        graph.add_node("intake", self._run_intake)
        graph.add_node("validation", self._validate_intake)
        graph.add_node("planner", self._run_planner)
        graph.add_node("research", self._run_parallel_research)
        graph.add_node("synthesizer", self._run_synthesizer)
        graph.add_node("writer", self._run_writer)

        graph.add_edge(START, "intake")
        graph.add_edge("intake", "validation")
        graph.add_edge("validation", "planner")
        graph.add_edge("planner", "research")
        graph.add_edge("research", "synthesizer")
        graph.add_edge("synthesizer", "writer")
        graph.add_edge("writer", END)

        return graph.compile(checkpointer=MemorySaver())

    async def run(self, user_query: str, event_queue=None):
        state = PlannerState(user_query=user_query)
        state.status = "in_progress"
        self.trace.start_workflow(user_query)

        app_state = {
            "workflow": state.dict()
        }
        config = {"configurable": {"trace": self.trace}}

        result = await self.graph.invoke(app_state, config=config)
        workflow_state = result["workflow"]

        if event_queue is not None:
            await event_queue.put({"type": "trace", "payload": self.trace.summary()})

        return {
            "status": workflow_state.get("status", "failed"),
            "state": workflow_state,
            "message": None
        }

    async def _run_intake(self, state: MessagesState, config: dict = None):
        start = time.time()
        workflow = state["workflow"]
        output = await intake_node(workflow)
        duration_ms = int((time.time() - start) * 1000)
        self.trace.append("intake", "success" if output["success"] else "failed", duration_ms, output)
        return {"workflow": {**workflow, **output["payload"]}}

    async def _validate_intake(self, state: MessagesState, config: dict = None):
        workflow = state["workflow"]
        result = validate_intake(workflow)
        self.trace.append("validation", "success" if not result["errors"] else "failed", 0, result)
        if result["errors"]:
            workflow = {**workflow, "validation_errors": result["errors"], "status": "failed"}
            return {"workflow": workflow}
        workflow = {**workflow, **result["payload"]}
        return {"workflow": workflow}

    async def _run_planner(self, state: MessagesState, config: dict = None):
        workflow = state["workflow"]
        start = time.time()
        output = await planner_node(workflow)
        duration_ms = int((time.time() - start) * 1000)
        self.trace.append("planner", "success" if output["success"] else "failed", duration_ms, output)
        workflow = {**workflow, **output["payload"]}
        return {"workflow": workflow}

    async def _run_parallel_research(self, state: MessagesState, config: dict = None):
        workflow = state["workflow"]
        start = time.time()
        output = await research_node(workflow, self.trace)
        duration_ms = int((time.time() - start) * 1000)
        self.trace.append("research", "success" if output["success"] else "failed", duration_ms, output)
        workflow = {**workflow, **output["payload"]}
        return {"workflow": workflow}

    async def _run_synthesizer(self, state: MessagesState, config: dict = None):
        workflow = state["workflow"]
        start = time.time()
        output = await synthesis_node(workflow)
        duration_ms = int((time.time() - start) * 1000)
        self.trace.append("synthesizer", "success" if output["success"] else "failed", duration_ms, output)
        workflow = {**workflow, **output["payload"]}
        return {"workflow": workflow}

    async def _run_writer(self, state: MessagesState, config: dict = None):
        workflow = state["workflow"]
        start = time.time()
        output = await writer_node(workflow)
        duration_ms = int((time.time() - start) * 1000)
        self.trace.append("writer", "success" if output["success"] else "failed", duration_ms, output)
        workflow = {**workflow, **output["payload"]}
        return {"workflow": workflow}
