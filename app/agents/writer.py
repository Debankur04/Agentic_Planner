from app.prompts.prompts import writer_prompt
from app.schemas.outputs import NodeResult
from app.services.llm import LLMService

async def writer_node(workflow: dict) -> dict:
    synthesis = workflow.get("synthesis", {})
    if not synthesis:
        return NodeResult(success=False, payload={}, errors=["Writer received empty synthesis data"], warnings=[]).dict()

    prompt = writer_prompt(synthesis)
    response = await LLMService().render_markdown(prompt)
    return NodeResult(success=True, payload={"final_response": response}).dict()
