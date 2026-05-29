from __future__ import annotations
from typing import Any, Dict, Iterable, Optional, Union
from pydantic import BaseModel


def is_pydantic_model(value: Any) -> bool:
    return isinstance(value, BaseModel)


def safe_model_dump(value: Any, **kwargs: Any) -> Any:
    if isinstance(value, BaseModel):
        return value.model_dump(**kwargs)
    return value


def safe_to_dict(value: Any, deep: bool = True) -> Any:
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json" if deep else "python")
    if isinstance(value, dict):
        return {k: safe_to_dict(v, deep=deep) for k, v in value.items()}
    if isinstance(value, list):
        return [safe_to_dict(v, deep=deep) for v in value]
    if isinstance(value, tuple):
        return [safe_to_dict(v, deep=deep) for v in value]
    if isinstance(value, set):
        return [safe_to_dict(v, deep=deep) for v in value]
    return value


def safe_state_access(state: Any, key: str, default: Any = None) -> Any:
    if isinstance(state, BaseModel):
        return getattr(state, key, default)
    if isinstance(state, dict):
        return state.get(key, default)
    if hasattr(state, key):
        return getattr(state, key, default)
    return default


def safe_state_get(state: Any, path: str, default: Any = None) -> Any:
    if not path:
        return state
    parts = path.split('.')
    current: Any = state
    for part in parts:
        if isinstance(current, BaseModel):
            current = getattr(current, part, default)
        elif isinstance(current, dict):
            current = current.get(part, default)
        else:
            return default
        if current is None:
            return default
    return current
