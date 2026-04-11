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
    # Step 1: extract JSON block
    match = re.search(r'\{.*\}', raw_output, re.DOTALL)
    if not match:
        raise ValueError("No JSON object found")

    json_str = match.group()

    # Step 2: fix invalid control characters INSIDE strings
    def escape_control_chars(match):
        content = match.group(0)
        content = content.replace("\n", "\\n")
        content = content.replace("\t", "\\t")
        content = content.replace("\r", "\\r")
        return content

    # 🔥 only replace inside quoted strings
    json_str = re.sub(r'"(.*?)"', escape_control_chars, json_str, flags=re.DOTALL)

    # Step 3: parse safely
    return json.loads(json_str)
    
def validate_llm_output(raw_output: str) -> dict:
    """
    1. Enforce JSON structure
    2. Detect hallucination signals
    3. Length constraint check
    Returns validated content or raises OutputValidationError.
    """
    # Step 1: JSON parse
    print(f'here your raw output: {raw_output}')
    try:
        parsed = safe_json_parse(raw_output)
    except Exception:
        raise OutputValidationError("Response is not valid JSON")

    # Step 2: Required fields
    required = {"reply", "preference", "confidence"}
    missing = required - set(parsed.keys())
    if missing:
        raise OutputValidationError(f"Missing fields: {missing}")

    # Step 3: Hallucination heuristics
    reply = parsed.get("reply", "")
    HALLUCINATION_SIGNALS = [
        r"\$\d{4,}"   # only extremely large values       
        r"guaranteed price",
        r"confirmed booking",
        r"as of \d{4}",         # stale date claims
    ]
    for sig in HALLUCINATION_SIGNALS:
        if re.search(sig, reply, re.IGNORECASE):
            parsed["_hallucination_risk"] = True
            break

    # Step 4: Length guard (400–600 words)
    word_count = len(reply.split())
    if word_count < 50:
        raise OutputValidationError(f"Reply too short: {word_count} words")

    return parsed