import asyncio
import random
import time
from dataclasses import dataclass


@dataclass
class ModelInvocationError(Exception):
    error_class: str
    message: str
    node_name: str
    model_key: str | None = None

    def __str__(self) -> str:
        return f"{self.error_class}: {self.message}"


class ReliableModelGateway:
    def __init__(self, router):
        self.router = router
        router_config = getattr(router, "config", {})
        if not isinstance(router_config, dict):
            router_config = {}
        cfg = router_config.get("reliability", {})
        self.max_retries = int(cfg.get("max_retries", 2))
        self.base_backoff = float(cfg.get("base_backoff_seconds", 0.5))
        self.max_backoff = float(cfg.get("max_backoff_seconds", 4))

    def classify_error(self, exc: Exception) -> str:
        text = str(exc).lower()
        name = exc.__class__.__name__.lower()
        if "timeout" in text or "timeout" in name:
            return "provider_timeout"
        if "429" in text or "rate limit" in text or "too many requests" in text:
            return "provider_rate_limited"
        if "401" in text or "403" in text or "api key" in text or "auth" in text:
            return "provider_auth_error"
        if "json" in text or "malformed" in text:
            return "provider_malformed_output"
        if "unavailable" in text or "503" in text or "502" in text or "500" in text:
            return "provider_unavailable"
        return "provider_error"

    def _sleep_for_retry(self, retry_count: int):
        delay = min(self.max_backoff, self.base_backoff * (2 ** retry_count))
        delay += random.uniform(0, min(0.25, delay))
        time.sleep(delay)

    def invoke_node(self, node_name: str, prompt_messages: list, tools: list | None = None, trace=None, user_tier: str = "Pirate"):
        tools = tools or []
        excluded = set()
        candidates = self.router.candidate_models(node_name)
        last_error: ModelInvocationError | None = None

        for fallback_rank, model_key in enumerate(candidates):
            if model_key in excluded:
                continue
            try:
                llm = self.router.get_client(model_key)
            except Exception as exc:
                error_class = self.classify_error(exc)
                self.router.record_failure(model_key, exc)
                last_error = ModelInvocationError(error_class, str(exc), node_name, model_key)
                if trace:
                    trace.record("model_client_build_failed", {
                        "node": node_name,
                        "model_key": model_key,
                        "error_class": error_class,
                        "error": str(exc),
                    })
                continue

            if tools:
                llm = llm.bind_tools(tools)

            for retry_count in range(self.max_retries + 1):
                self.router.log_model_selection(
                    trace=trace,
                    node_name=node_name,
                    model_key=model_key,
                    fallback_rank=fallback_rank,
                    retry_count=retry_count,
                    error_class=last_error.error_class if last_error else "",
                )
                t0 = time.time()
                try:
                    response = llm.invoke(prompt_messages)
                    latency_ms = (time.time() - t0) * 1000
                    self.router.record_success(model_key, latency_ms)
                    if trace:
                        trace.record("model_invocation_success", {
                            "node": node_name,
                            "model_key": model_key,
                            "retry_count": retry_count,
                        }, latency_ms=latency_ms)
                    return response
                except Exception as exc:
                    error_class = self.classify_error(exc)
                    self.router.record_failure(model_key, exc)
                    last_error = ModelInvocationError(error_class, str(exc), node_name, model_key)
                    if trace:
                        trace.record("model_invocation_failed", {
                            "node": node_name,
                            "model_key": model_key,
                            "retry_count": retry_count,
                            "error_class": error_class,
                            "error": str(exc)[:500],
                        }, latency_ms=(time.time() - t0) * 1000)

                    if retry_count < self.max_retries and error_class in {
                        "provider_timeout",
                        "provider_rate_limited",
                        "provider_unavailable",
                        "provider_error",
                    }:
                        self._sleep_for_retry(retry_count)
                        continue
                    break

            excluded.add(model_key)

        raise ModelInvocationError(
            "all_providers_unavailable",
            str(last_error) if last_error else f"No candidates configured for node={node_name}",
            node_name,
            last_error.model_key if last_error else None,
        )

    async def ainvoke_node(self, *args, **kwargs):
        return await asyncio.to_thread(self.invoke_node, *args, **kwargs)
