from langchain_core.messages import SystemMessage
from llmops.prompt_registry import PromptRegistry

registry = PromptRegistry(
    base_dir="agent_file/prompt_library/versions"
)

prompt_version = registry.get_active()
system_prompt = prompt_version.content

SYSTEM_PROMPT = SystemMessage(
    content=system_prompt
)