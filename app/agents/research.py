import asyncio
from app.prompts.prompts import research_prompt
from app.schemas.outputs import NodeResult
from app.services.llm import LLMService
from app.services.json_recovery import safe_parse_json

async def _flight_research(intake: dict, planner: dict) -> dict:
    prompt = research_prompt("flight information", intake, planner)
    response = await LLMService().extract_structured(prompt)
    payload = safe_parse_json(response, expected_keys=["flight_options", "estimated_cost"])
    return {"flights": payload or {}}

async def _hotel_research(intake: dict, planner: dict) -> dict:
    prompt = research_prompt("hotel availability", intake, planner)
    response = await LLMService().extract_structured(prompt)
    payload = safe_parse_json(response, expected_keys=["hotel_options", "estimated_cost"])
    return {"hotels": payload or {}}

async def _budget_research(intake: dict, planner: dict) -> dict:
    prompt = research_prompt("budget planning", intake, planner)
    response = await LLMService().extract_structured(prompt)
    payload = safe_parse_json(response, expected_keys=["total_cost", "cost_breakdown", "remaining_budget"])
    return {"budget": payload or {}}

async def _visa_research(intake: dict, planner: dict) -> dict:
    prompt = research_prompt("visa requirements", intake, planner)
    response = await LLMService().extract_structured(prompt)
    payload = safe_parse_json(response, expected_keys=["visa_type", "processing_time_days", "cost_inr", "documentation"])
    return {"visa": payload or {}}

async def _activities_research(intake: dict, planner: dict) -> dict:
    prompt = research_prompt("activity recommendations", intake, planner)
    response = await LLMService().extract_structured(prompt)
    payload = safe_parse_json(response, expected_keys=["activities", "activity_cost_estimate"])
    return {"activities": payload or {}}

async def research_node(workflow: dict, trace):
    intake = workflow.get("intake", {})
    planner = workflow.get("planner", {})
    tasks = [
        _flight_research(intake, planner),
        _hotel_research(intake, planner),
        _budget_research(intake, planner),
        _visa_research(intake, planner),
        _activities_research(intake, planner)
    ]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    payload = {}
    errors = []
    warnings = []
    outputs = ["flights", "hotels", "budget", "visa", "activities"]

    for idx, result in enumerate(results):
        node_name = outputs[idx]
        if isinstance(result, Exception):
            errors.append(f"{node_name} research failed: {result}")
            payload[node_name] = {}
            warnings.append(f"{node_name} research returned empty due to error")
        else:
            payload.update(result)
    
    success = len(errors) == 0
    return NodeResult(success=success, payload=payload, errors=errors, warnings=warnings).dict()
