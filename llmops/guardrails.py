import json,re
from functools import lru_cache

# ---- Layer 1: Pattern blocklist ----
INJECTION_PATTERNS = [
    r"ignore (previous|all) instructions",
    r"you are now",
    r"pretend (you are|to be)",
    r"jailbreak",
    r"DAN mode",
    r"act as (?!a travel)",        # allow "act as a travel agent"
    r"forget your (system|instructions)",
    r"<\s*(script|iframe|object)",  # HTML injection
]

PII_PATTERNS = {
    "credit_card": r"\b\d{4}[\s-]?\d{4}[\s-]?\d{4}[\s-]?\d{4}\b",
    "ssn":         r"\b\d{3}-\d{2}-\d{4}\b",
    "passport":    r"\b[A-Z]{1,2}\d{6,9}\b",
}


def sanitize_input(user_input: str) -> tuple[str, list[str]]:
    """Returns (sanitized_input, list_of_violations)."""
    violations = []

    for pattern in INJECTION_PATTERNS:
        if re.search(pattern, user_input, re.IGNORECASE):
            violations.append(f"injection_attempt: {pattern}")

    # PII masking (before sending to LLM)
    sanitized = user_input
    for pii_type, pattern in PII_PATTERNS.items():
        sanitized = re.sub(pattern, f"[REDACTED_{pii_type.upper()}]", sanitized)

    return sanitized, violations


# Tool access restriction matrix
# TOOL_ACCESS_MATRIX = {
#     "free":     ["search_attractions", "search_restaurants", "get_current_weather"],
#     "standard": ["find_flights", "search_hotel", "search_attractions",
#                  "search_restaurants", "search_activities", "search_transportation",
#                  "get_current_weather", "get_weather_forecast"],
#     "premium":  "__all__",
# }

# def get_allowed_tools(user_tier: str, all_tools: list) -> list:
#     allowed = TOOL_ACCESS_MATRIX.get(user_tier, [])
#     if allowed == "__all__":
#         return all_tools
#     return [t for t in all_tools if t.name in allowed]

class OutputValidationError(Exception):
    pass

def safe_json_parse(raw_output: str):
    import json, re

    match = re.search(r'\{.*\}', raw_output, re.DOTALL)
    if not match:
        raise ValueError("No JSON object found")

    json_str = match.group()

    # 🔥 FIX 1: remove line-continuation backslashes
    json_str = re.sub(r'\\\n', '', json_str)

    # 🔥 FIX 2: normalize newlines
    json_str = json_str.replace('\n', '\\n')

    return json.loads(json_str)


    
def validate_llm_output(raw_output: str) -> str:
    """
    Validate plain text LLM output.
    """

    if not isinstance(raw_output, str):
        raise OutputValidationError("Output must be a string")

    reply = raw_output.strip()

    # Length check
    word_count = len(reply.split())
    if word_count < 50:
        raise OutputValidationError(f"Reply too short: {word_count} words")

    # Optional: basic hallucination signals
    HALLUCINATION_SIGNALS = [
        r"\$\d{4,}",
        r"guaranteed price",
        r"confirmed booking",
        r"as of \d{4}",
    ]

    for sig in HALLUCINATION_SIGNALS:
        if re.search(sig, reply, re.IGNORECASE):
            print("⚠️ Hallucination risk detected")

    return reply