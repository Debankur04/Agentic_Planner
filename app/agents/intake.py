import asyncio
from typing import Any
from app.schemas.outputs import NodeResult
from app.prompts.prompts import intake_prompt
from app.services.llm import LLMService
from app.services.json_recovery import safe_parse_json

async def intake_node(workflow: dict) -> dict:
    user_query = workflow["user_query"]
    prompt = intake_prompt(user_query)
    response_text = await LLMService().extract_structured(prompt)
    payload = safe_parse_json(
        response_text,
        expected_keys=["destination", "duration_days", "budget_inr", "travelers", "preferences", "constraints"]
    )
    if payload is None:
        return NodeResult(success=False, payload={}, errors=["Malformed intake extraction"], warnings=[]).dict()
    return NodeResult(success=True, payload={"intake": payload}).dict()
