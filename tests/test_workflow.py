import json
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from agent_file.agent.agentic_workflow import AgentRunner, GraphBuilder
from langchain_core.messages import AIMessage, HumanMessage


class FakeLLMResponse(AIMessage):
    def __init__(self, content, tool_calls=None):
        super().__init__(content=content)
        self.tool_calls = tool_calls or []


def test_full_flow_no_clarification(monkeypatch):
    router = Mock()
    responses = [
        FakeLLMResponse(content='{"plan":"details"}', tool_calls=[]),
        FakeLLMResponse(content="Research complete and feasible.", tool_calls=[]),
        FakeLLMResponse(content='{"decision":"pass","reason":"Looks feasible","missing_information":[]}', tool_calls=[]),
        FakeLLMResponse(content="Final itinerary ready.", tool_calls=[]),
    ]

    def fake_invoke(self, messages, state, config, agent_name, tools):
        return responses.pop(0)

    monkeypatch.setattr(GraphBuilder, "_invoke_llm", fake_invoke)
    agent_runner = AgentRunner(router)

    output = agent_runner.run_agent(
        user_input="Plan a trip to Paris",
        user_id="user1",
        conversation_id="conv_full"
    )

    assert output["messages"][-1].content == "Final itinerary ready."
    assert output.get("hitl_question") is None


@pytest.mark.skip(reason="ask_human HITL path is disabled in the current workflow")
def test_ask_human_then_resume(monkeypatch):
    router = Mock()
    responses = [
        FakeLLMResponse(content='{"plan":"details"}', tool_calls=[]),
        FakeLLMResponse(content="", tool_calls=[
            {"name": "ask_human", "args": {"question": "What is your budget?"}, "id": "ask1"}
        ]),
        FakeLLMResponse(content="Final itinerary ready after budget clarification.", tool_calls=[]),
    ]

    def fake_invoke(self, messages, state, config, agent_name, tools):
        return responses.pop(0)

    monkeypatch.setattr(GraphBuilder, "_invoke_llm", fake_invoke)
    agent_runner = AgentRunner(router)

    first_output = agent_runner.run_agent(
        user_input="Plan a trip to Paris",
        user_id="user2",
        conversation_id="conv_budget"
    )

    assert first_output.get("hitl_question") == "What is your budget?"

    second_output = agent_runner.run_agent(
        user_input="I can spend 1500",
        user_id="user2",
        conversation_id="conv_budget"
    )

    assert second_output["messages"][-1].content == "Final itinerary ready after budget clarification."
    assert second_output.get("hitl_question") is None


def test_repeated_tool_detection_exits():
    builder = GraphBuilder(Mock())
    duplicate_tool_call = {"name": "search_hotel", "args": {"location": "Paris"}}
    state = {
        "messages": [
            SimpleNamespace(tool_calls=[duplicate_tool_call]),
            SimpleNamespace(tool_calls=[duplicate_tool_call])
        ],
        "workflow_state": {"validation_decision": "pass"}
    }

    assert builder.should_continue(state) == "validator"


def test_completion_checks_reject_non_writer_final(monkeypatch):
    router = Mock()
    agent_runner = AgentRunner(router)
    trace = Mock()
    output = {
        "workflow_state": {
            "planning_output": "plan",
            "research_output": "research",
            "validation_output": {"decision": "pass"},
            "writer_output": "",
            "final_user_response": "research",
        }
    }

    with pytest.raises(RuntimeError):
        agent_runner._validate_final_output(output, trace)
