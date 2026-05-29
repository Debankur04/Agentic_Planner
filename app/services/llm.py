from typing import Any
from langchain.llms.base import LLM
from langchain.llms import OpenAI
from app.services.json_recovery import safe_parse_json


class LLMService:
    def __init__(self):
        self.client = OpenAI(temperature=0.2, model_name="gpt-4o")

    async def extract_structured(self, prompt: str) -> str:
        response = await self.client.apredict(prompt)
        return response

    async def render_markdown(self, prompt: str) -> str:
        response = await self.client.apredict(prompt)
        return response
