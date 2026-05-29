from typing import Any


def intake_prompt(user_query: str) -> str:
    return (
        "Extract structured travel requirements from the user's request. "
        "Return valid JSON only with keys: destination, duration_days, budget_inr, travelers, preferences, constraints. "
        f"User request: {user_query}"
    )


def planner_prompt(intake: dict) -> str:
    return (
        "Given the extracted travel intake, create a structured high-level travel plan with cities, duration_days, style, daily_pacing, and budget_allocation. "
        "Return valid JSON only. "
        f"Intake: {intake}"
    )


def research_prompt(topic: str, intake: dict, planner: dict) -> str:
    return (
        f"Research {topic} for the trip described by intake and planner data. "
        "Return valid JSON only. "
        f"Intake: {intake} Planner: {planner}"
    )


def synthesis_prompt(workflow: dict) -> str:
    return (
        "Merge the workflow research results into a consistent travel synthesis. "
        "Return valid JSON only with keys: itinerary, feasibility, remaining_balance, notes. "
        f"Workflow: {workflow}"
    )


def writer_prompt(synthesis: dict) -> str:
    return (
        "Render the final travel plan as a markdown itinerary. "
        "Do not invent extra research; use only the provided structured synthesis. "
        f"Synthesis: {synthesis}"
    )
