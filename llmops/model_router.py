"""
Node-aware model router.

The router is intentionally small: it owns provider client construction,
model health, node-level selection, and model decision logging. Retry and
fallback orchestration lives in ReliableModelGateway.
"""
import os
import time
from collections import deque
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_groq import ChatGroq
from langchain_openai import ChatOpenAI


class ModelTier(Enum):
    CHEAP = "cheap"
    EXPENSIVE = "expensive"


@dataclass
class ModelHealth:
    error_count: int = 0
    total_calls: int = 0
    latencies: deque = field(default_factory=lambda: deque(maxlen=100))
    circuit_open: bool = False
    circuit_open_until: float = 0.0

    @property
    def error_rate(self) -> float:
        if self.total_calls == 0:
            return 0.0
        return self.error_count / self.total_calls

    @property
    def p99_latency(self) -> float:
        if not self.latencies:
            return 0.0
        sorted_lat = sorted(self.latencies)
        idx = min(len(sorted_lat) - 1, int(len(sorted_lat) * 0.99))
        return sorted_lat[idx]

    def is_healthy(self) -> bool:
        if self.circuit_open:
            if time.time() > self.circuit_open_until:
                self.circuit_open = False
                return True
            return False
        if self.total_calls < 10:
            return True
        return self.error_rate < 0.10 and self.p99_latency < 3000


class ModelRouter:
    def __init__(self, config: dict):
        self.config = config
        self.health: dict[str, ModelHealth] = {
            key: ModelHealth() for key in config.get("models", {})
        }
        self._clients: dict[str, object] = {}

    def _build_client(self, model_key: str):
        cfg = self.config["models"][model_key]
        provider = cfg["provider"]
        model_name = cfg["model_name"]

        if provider == "groq":
            return ChatGroq(model=model_name, api_key=os.getenv("GROQ_API_KEY"))

        if provider == "gemini":
            return ChatGoogleGenerativeAI(
                model=model_name,
                google_api_key=os.getenv("GEMINI_API_KEY"),
            )

        if provider == "mistral":
            return ChatOpenAI(
                model=model_name,
                api_key=os.getenv("MISTRAL_API_KEY"),
                base_url=os.getenv("MISTRAL_BASE_URL", "https://api.mistral.ai/v1"),
            )

        if provider == "openai_compatible":
            return ChatOpenAI(
                model=model_name,
                api_key=os.getenv("OPENROUTER_API_KEY"),
                base_url="https://openrouter.ai/api/v1",
                extra_body={
                    "reasoning": {
                        "enabled": True
                    }
                }
            )
        raise ValueError(f"Unknown provider: {provider}")

    def get_client(self, model_key: str):
        if model_key not in self._clients:
            self._clients[model_key] = self._build_client(model_key)
        return self._clients[model_key]

    def get_llm(self, agent_name: str, query: str = "", user_tier: str = "Pirate"):
        model_key = self.select_model(agent_name, user_tier=user_tier)
        return self.get_client(model_key)

    def candidate_models(self, node_name: str, exclude_models: Optional[set] = None) -> list[str]:
        exclude_models = exclude_models or set()
        node_cfg = self.config.get("node_routing", {}).get(node_name, {})
        candidates = []
        primary = node_cfg.get("primary")
        if primary:
            candidates.append(primary)
        candidates.extend(node_cfg.get("fallback", []))

        if not candidates:
            rules = self.config.get("routing_rules", {})
            default_model = rules.get("default_model")
            if default_model:
                candidates.append(default_model)
            candidates.extend(rules.get("fallback_chain", []))

        deduped = []
        for model_key in candidates:
            if model_key in self.health and model_key not in exclude_models and model_key not in deduped:
                deduped.append(model_key)
        return deduped

    def select_model(self, node_name: str, user_tier: str = "Pirate", exclude_models: Optional[set] = None) -> str:
        for model_key in self.candidate_models(node_name, exclude_models=exclude_models):
            if self.health[model_key].is_healthy():
                return model_key
        raise RuntimeError(f"All models unhealthy for node={node_name}")

    def record_success(self, model_key: str, latency_ms: float):
        h = self.health[model_key]
        h.total_calls += 1
        h.latencies.append(latency_ms)

    def record_failure(self, model_key: str, error: Exception | str):
        h = self.health[model_key]
        h.total_calls += 1
        h.error_count += 1
        threshold_pct = self.config.get("routing_rules", {}).get("error_threshold_pct", 5)
        if h.total_calls >= 3 and h.error_rate > (threshold_pct / 100):
            cooldown = self.config.get("reliability", {}).get("circuit_cooldown_seconds", 60)
            h.circuit_open = True
            h.circuit_open_until = time.time() + cooldown

    def log_model_selection(self, trace, node_name: str, model_key: str, fallback_rank: int = 0, retry_count: int = 0, error_class: str = ""):
        cfg = self.config.get("models", {}).get(model_key, {})
        health = self.health.get(model_key)
        data = {
            "node": node_name,
            "model_key": model_key,
            "provider": cfg.get("provider"),
            "model_name": cfg.get("model_name"),
            "fallback_rank": fallback_rank,
            "retry_count": retry_count,
            "error_class": error_class,
            "circuit_open": bool(health and health.circuit_open),
        }
        if trace:
            trace.record("model_selected", data)
        else:
            print(f"[ModelRouter] {data}")
