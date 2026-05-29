import json
from datetime import datetime, date
from uuid import UUID
from pydantic import BaseModel
from typing import Any


def safe_jsonable_encoder(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, BaseModel):
        return safe_jsonable_encoder(value.model_dump())
    if isinstance(value, dict):
        return {safe_jsonable_encoder(k): safe_jsonable_encoder(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [safe_jsonable_encoder(v) for v in value]
    if hasattr(value, "model_dump") and callable(value.model_dump):
        try:
            return safe_jsonable_encoder(value.model_dump())
        except Exception:
            pass
    if hasattr(value, "dict") and callable(value.dict):
        try:
            return safe_jsonable_encoder(value.dict())
        except Exception:
            pass
    if hasattr(value, "__iter__") and not isinstance(value, (str, bytes, bytearray)):
        try:
            return [safe_jsonable_encoder(v) for v in value]
        except Exception:
            pass
    return str(value)


def safe_serialize_response(payload: Any) -> str:
    try:
        return json.dumps(safe_jsonable_encoder(payload), ensure_ascii=False)
    except Exception as exc:
        raise RuntimeError(f"Serialization failed: {exc}") from exc
