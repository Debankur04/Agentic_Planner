from typing import Any

REQUIRED_FIELDS = ["destination", "duration_days", "budget_inr", "travelers"]


def validate_intake(workflow: dict) -> dict:
    intake = workflow.get("intake", {})
    errors = []
    warnings = []

    if not intake:
        return {"errors": ["No intake data extracted"], "payload": {}}

    if not intake.get("destination"):
        errors.append("missing destination")
    if not intake.get("duration_days"):
        errors.append("missing duration")
    budget = intake.get("budget_inr")
    if budget is None or not isinstance(budget, (int, float)) or budget <= 0:
        errors.append("invalid budget")
    travelers = intake.get("travelers")
    if travelers is None or not isinstance(travelers, int) or travelers < 1:
        errors.append("invalid travelers count")

    if intake.get("constraints") and "budget" in str(intake.get("constraints")).lower():
        warnings.append("Budget constraints are embedded in constraints. Prefer explicit budget_inr.")

    payload = {"validation_errors": errors, "warnings": warnings}
    return {"errors": errors, "payload": payload}
