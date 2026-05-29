from app.prompts.prompts import synthesis_prompt
from app.schemas.outputs import NodeResult
from app.services.llm import LLMService
from app.services.json_recovery import safe_parse_json

async def synthesis_node(workflow: dict) -> dict:
    prompt = synthesis_prompt(workflow)
    response = await LLMService().extract_structured(prompt)
    result = safe_parse_json(response, expected_keys=["itinerary", "feasibility", "remaining_balance", "notes"])
    if result is None:
        return NodeResult(success=False, payload={}, errors=["Synthesis failed malformed JSON"], warnings=[]).dict()
    return NodeResult(success=True, payload={"synthesis": result}).dict()
