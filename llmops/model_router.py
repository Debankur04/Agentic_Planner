"""
Production model router with:
  - Cost-aware routing (cheap vs. expensive selection)
  - Latency-aware switching (rolling p99 window)
  - Automatic failover with circuit-breaker pattern
  - Cooldown after failure (exponential backoff)
"""
import time, asyncio
from collections import deque
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional
from langchain_groq import ChatGroq
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import SystemMessage, HumanMessage
from backend.mongo import save_intent


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
        idx = int(len(sorted_lat) * 0.99)
        return sorted_lat[idx]

    def is_healthy(self) -> bool:
        if self.circuit_open:
            if time.time() > self.circuit_open_until:
                self.circuit_open = False   # half-open
                return True
            return False
        if self.total_calls < 30:
            return True
        return self.error_rate < 0.05 and self.p99_latency < 3000


class ModelRouter:
    def __init__(self, config: dict):
        self.config = config
        self.health: dict[str, ModelHealth] = {
            k: ModelHealth() for k in config["models"]
        }
        self._clients: dict[str, object] = {}

    def _build_client(self, model_key: str):
        cfg = self.config["models"][model_key]
        if cfg["provider"] == "groq":
            import os
            return ChatGroq(model=cfg["model_name"], api_key=os.getenv("GROQ_API_KEY"))
        elif cfg["provider"] == "gemini":
            import os
            return ChatGoogleGenerativeAI(
                model=cfg["model_name"], google_api_key=os.getenv("GEMINI_API_KEY")
            )
        raise ValueError(f"Unknown provider: {cfg['provider']}")

    def get_client(self, model_key: str):
        if model_key not in self._clients:
            self._clients[model_key] = self._build_client(model_key)
        return self._clients[model_key]

    def _classify_intent(self, query: str) -> bool:
        """Returns True if the query is a simple factual/greeting question, False if complex/reasoning."""
        try:
            # Use the cheapest/fastest model available
            candidate = self.config["routing_rules"].get("simple_query_model", "fast")
            client = self.get_client(candidate)
            prompt = [
                SystemMessage(content="You are an intent classifier. Return strictly 'True' if the user query is a simple factual question or greeting (e.g., asking for weather, definitions). Return strictly 'False' if it is a complex query requiring multi-step planning, reasoning, or external data processing (e.g., travel planning, complex searches). Output nothing else but True or False."),
                HumanMessage(content=query)
            ]
            response = client.invoke(prompt)
            result = response.content.strip().lower()
            # Eliminate weird trailing punctuation or whitespace
            return "true" in result
        except Exception as e:
            print(f"Classifier error: {e}")
            return False

    def select_model(self, query: str, user_tier: str = "standard", exclude_models: set = None) -> str:
        """Route to cheapest healthy model that meets quality bar."""
        rules = self.config["routing_rules"]
        exclude_models = exclude_models or set()

        if rules.get("use_intent_classifier", False):
            intent = self._classify_intent(query)
            save_intent(query= query, intent= intent)
            if intent:
                candidate = rules["simple_query_model"]
                if candidate not in exclude_models and self.health[candidate].is_healthy():
                    return candidate

        # Walk the fallback chain
        for model_key in rules["fallback_chain"]:
            if model_key not in exclude_models and self.health[model_key].is_healthy():
                return model_key

        raise RuntimeError("All models unhealthy — serving degraded response")

    def record_success(self, model_key: str, latency_ms: float):
        h = self.health[model_key]
        h.total_calls += 1
        h.latencies.append(latency_ms)

    def record_failure(self, model_key: str, error: Exception):
        h = self.health[model_key]
        h.total_calls += 1
        h.error_count += 1
        if h.error_rate > 0.05:
            h.circuit_open = True
            h.circuit_open_until = time.time() + 60   # 60s cooldown