from app.schemas.outputs import NodeResult
from app.prompts.prompts import planner_prompt
from app.services.llm import LLMService
from app.services.json_recovery import safe_parse_json

async def planner_node(workflow: dict) -> dict:
    intake = workflow.get("intake", {})
    if not intake:
        return NodeResult(success=False, payload={}, errors=["Planner received empty intake data"], warnings=[]).dict()

    prompt = planner_prompt(intake)
    response_text = await LLMService().extract_structured(prompt)
    payload = safe_parse_json(
        response_text,
        expected_keys=["cities", "duration_days", "style", "daily_pacing", "budget_allocation"],
    )
    if payload is None:
        return NodeResult(success=False, payload={}, errors=["Planner output malformed JSON"], warnings=[]).dict()

    return NodeResult(success=True, payload={"planner": payload}).dict()
