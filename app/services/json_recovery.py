import json
from typing import Any


def safe_parse_json(raw: str, expected_keys: list[str] | None = None) -> dict | None:
    raw = raw.strip()
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        parsed = None

    if parsed is not None:
        if expected_keys and not all(key in parsed for key in expected_keys):
            return None
        return parsed

    repaired = _repair_json(raw)
    if repaired is None:
        return None
    if expected_keys and not all(key in repaired for key in expected_keys):
        return None
    return repaired


def _repair_json(raw: str) -> dict | None:
    json_text = _extract_json_block(raw)
    if not json_text:
        return None
    try:
        return json.loads(json_text)
    except json.JSONDecodeError:
        cleaned = _cleanup_json(json_text)
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            return None


def _extract_json_block(text: str) -> str | None:
    start = text.find("{")
    if start == -1:
        return None
    depth = 0
    for idx, char in enumerate(text[start:], start=start):
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return text[start:idx + 1]
    return None


def _cleanup_json(text: str) -> str:
    text = text.replace("\n", " ")
    text = text.replace("\r", " ")
    text = text.replace("\t", " ")
    text = text.replace(", }", "}")
    text = text.replace(", ]", "]")
    return text.strip()
