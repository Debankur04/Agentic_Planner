# Multi-Agent Workflow Prompts

from pathlib import Path
from datetime import date
import re
from typing import Literal, Optional

PROMPT_LIBRARY_DIR = Path(__file__).parent
INTAKE_VALIDATION_PROMPT_DIR = PROMPT_LIBRARY_DIR / "intake_validator_prompt"
RESEARCH_PRICING_PROMPT_DIR = PROMPT_LIBRARY_DIR / "research_pricing_prompt"
WRITER_PROMPT_DIR = PROMPT_LIBRARY_DIR / "writer_prompt"


def _load_latest_prompt_text(prompt_dir: Path) -> Optional[str]:
    if not prompt_dir.exists() or not prompt_dir.is_dir():
        return None
    prompt_files = [p for p in prompt_dir.glob("*.txt") if p.is_file()]
    if not prompt_files:
        return None

    def _numeric_sort_key(path: Path):
        matches = re.findall(r"\d+", path.stem)
        number = int(matches[-1]) if matches else 0
        return (number, path.name)

    latest_prompt = max(prompt_files, key=_numeric_sort_key)
    return latest_prompt.read_text(encoding="utf-8")


def build_intake_prompt(
    user_input: str,
    preference: str = "",
    history: str = "",
    memory: str = "",
    research_agent_input: str = "",
    stage: Literal["planning", "validation"] = "planning"
) -> tuple[str, str]:
    if research_agent_input:
        stage = "validation"

    system_prompt = _load_latest_prompt_text(INTAKE_VALIDATION_PROMPT_DIR)
    user_prompt = f"""Stage: {stage}

User Preferences: {preference}

Recent Messages:
{history}

Relevant Memory:
{memory}
    
Today's Date: {date.today().isoformat()}

Original User Request:
{user_input}

Research Agent Input:
{research_agent_input if research_agent_input else "Not yet available — this is the planning stage."}

If any travel detail is missing, assume a reasonable practical value and mark it as an assumption.
Do not ask the user for more information.
"""
    return system_prompt, user_prompt


def build_research_prompt(
    user_input: str,
    intake_plan: str,
    research_instructions: str,
    preference: str = "",
    history: str = "",
    memory: str = "",
    previous_tool_results: dict | None = None,
    clarification_history: dict | None = None,
) -> tuple[str, str]:
    """
    Builds the Research & Pricing Agent prompt.
    """
    system_prompt = _load_latest_prompt_text(RESEARCH_PRICING_PROMPT_DIR)
    prev_tools = previous_tool_results or {}
    clar = clarification_history or {}
    user_prompt = f"""User request:
{user_input}

Intake plan:
{intake_plan}

Preference:
{preference}

Recent Messages:
{history}

Relevant Memory:
{memory}

Previous tool results (do not re-run tools that already have results):
{prev_tools}

Clarification history (if any):
{clar}

Research Instructions:
{research_instructions}

If a required detail is missing, assume a reasonable value and note it as an assumption. Avoid repeating identical tool calls if results are already present.
"""
    return system_prompt, user_prompt


def build_writer_prompt(
    user_input: str,
    validated_summary: str,
    tool_results,
    preference: str = "",
    relevant_memory: str = "",
) -> tuple[str, str]:
    """
    Builds the Writer Agent prompt.
    """
    system_prompt = _load_latest_prompt_text(WRITER_PROMPT_DIR)
    user_prompt = f"""Original User Request:
{user_input}

Preference:
{preference}

Relevant memory:
{relevant_memory}

Tool Results:

{tool_results}

Validated Travel Summary from Intake Agent:
{validated_summary}

If any detail is missing, assume a reasonable value and note it as an assumption. Do not ask the user for more information.

Write the final response for the user.
"""
    return system_prompt, user_prompt
