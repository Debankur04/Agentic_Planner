import asyncio
import json
import re
import time
import traceback
import uuid

from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.messages import HumanMessage, SystemMessage

from agent_file.agent.agentic_workflow import AgentRunner, TravelEngine
from agent_file.utils.config_loader import load_config
from backend.supabase_client.db_operations import add_message, get_preference
from llmops.guardrails import sanitize_input, validate_llm_output
from llmops.model_router import ModelRouter
from llmops.trace_service import ExecutionTrace
from service.cache_service import redis_client
from service.context_manager import ContextManager
from service.quota_service import QuotaService


router = ModelRouter(load_config())
runner = AgentRunner(router)
travel_engine = TravelEngine(runner)

quota_service = QuotaService(redis_client=redis_client)
cfg = load_config()
memory_cfg = cfg.get("memory", {})
context_manager = ContextManager(
    recent_limit=int(memory_cfg.get("recent_message_limit", 8)),
    memory_limit=int(memory_cfg.get("relevant_memory_limit", 5)),
    max_memory_chars=int(memory_cfg.get("max_memory_text_chars", 600)),
)


def fallback_to_json(raw_output: str):
    response = runner.fallback_json_agent(raw_input=raw_output)
    content = response.content if hasattr(response, "content") else str(response)
    try:
        match = re.search(r"\{.*\}", content, re.DOTALL)
        if match:
            json_str = match.group()
            json_str = re.sub(r"\\\n", "", json_str)
            json_str = json_str.replace("\n", "\\n")
            parsed = json.loads(json_str)
            if "reply" in parsed:
                return parsed["reply"]
    except Exception:
        pass
    return content


def process_llm_output(raw_output: str):
    try:
        return validate_llm_output(raw_output)
    except Exception:
        return fallback_to_json(raw_output)


def clean_llm_output(text: str) -> str:
    text = re.sub(r"<function=.*?>.*?</function>", "", str(text or ""), flags=re.DOTALL)
    text = re.sub(r"<function=.*?>", "", text)
    text = re.sub(r"\n\s*\n", "\n\n", text)
    return text.strip()


class QueueCallbackHandler(BaseCallbackHandler):
    def __init__(self, q, loop):
        self.q = q
        self.loop = loop

    def emit_event(self, event: dict) -> None:
        if event:
            self.loop.call_soon_threadsafe(self.q.put_nowait, event)

    def on_agent_event(self, event: dict) -> None:
        self.emit_event(event)

    def on_llm_new_token(self, token: str, **kwargs) -> None:
        if token:
            self.loop.call_soon_threadsafe(self.q.put_nowait, token)


def chunk_text(text: str, chunk_size: int = 48):
    text = str(text or "")
    for start in range(0, len(text), chunk_size):
        yield text[start:start + chunk_size]


def _load_preference(user_id: str, trace: ExecutionTrace) -> str:
    t0 = time.time()
    try:
        pref_data = get_preference(user_id)
        if isinstance(pref_data, list) and pref_data:
            preference = json.dumps({
                "dietary": pref_data[0].get("dietary_preference"),
                "custom": pref_data[0].get("custom_preference"),
            })
        else:
            preference = ""
    except Exception as exc:
        preference = ""
        trace.record("preference_fetch_failed", {"error": str(exc)})
    trace.record("preference_fetched", {"has_preference": bool(preference)}, latency_ms=(time.time() - t0) * 1000)
    return preference


def _extract_durable_memory(user_query: str, final_output: str, trace: ExecutionTrace) -> str:
    fallback = (
        f"User query: {user_query}\n"
        f"Durable assistant summary: {str(final_output)[:500]}"
    )
    prompt = [
        SystemMessage(content=(
            "Extract only durable travel-planning memory from the exchange. "
            "Keep reusable preferences, constraints, accessibility needs, budget style, food preferences, "
            "home/base city, and recurring travel patterns. "
            "Do not store one-off itinerary details, prices, transient dates, or tool results. "
            "Return a concise plain-text bullet list. Return an empty string if there is no durable memory."
        )),
        HumanMessage(content=f"User query:\n{user_query}\n\nFinal assistant response:\n{final_output}"),
    ]
    try:
        response = runner.graph_builder.gateway.invoke_node(
            node_name="memory",
            prompt_messages=prompt,
            tools=[],
            trace=trace,
        )
        extracted = str(getattr(response, "content", "")).strip()
        if extracted and extracted.lower() not in {"none", "no durable memory", "empty"}:
            trace.record("memory_extraction_completed", {"memory_length": len(extracted)})
            return extracted
    except Exception as exc:
        trace.record("memory_extraction_failed", {"error": str(exc)})
    return fallback


async def query_helper(query):
    request_id = f"req_{uuid.uuid4().hex}"
    trace = ExecutionTrace(request_id=request_id)
    t0 = time.time()
    trace.record("query_start", {
        "request_id": request_id,
        "user_id": query.user_id,
        "conversation_id": query.conversation_id,
        "question_preview": query.question[:200],
    })

    quota_reserved = False
    try:
        user_query, violation = sanitize_input(query.question)
        if violation:
            trace.record("guardrail_violation", {"question_preview": query.question[:200]})
            return {
                "error": {"message": "Message violation detected", "code": "guardrail_violation"},
                "trace_id": request_id,
            }
        trace.record("guardrail_pass", {"sanitised_preview": user_query[:200]})

        quota_status = quota_service.check_and_reserve_message(query.user_id, request_id)
        quota_reserved = quota_status.allowed
        trace.record("quota_checked", quota_status.to_dict())
        if not quota_status.allowed:
            return {
                "error": {
                    "message": quota_status.message or "Weekly message quota exceeded.",
                    "code": "quota_exceeded",
                    "quota": quota_status.to_dict(),
                },
                "trace_id": request_id,
            }

        preference = _load_preference(query.user_id, trace)

        t_ctx = time.time()
        context_bundle = context_manager.build_context_bundle(
            user_id=query.user_id,
            conversation_id=query.conversation_id,
            current_query=user_query,
            trace=trace,
        )
        trace.record("context_bundle_built", {
            "recent_message_count": len(context_bundle.get("recent_messages", [])),
            "relevant_memory_length": len(context_bundle.get("relevant_memory", "")),
        }, latency_ms=(time.time() - t_ctx) * 1000)

        t_db = time.time()
        add_message(query.user_id, query.conversation_id, "user", user_query)
        trace.record("db_user_message_saved", {}, latency_ms=(time.time() - t_db) * 1000)

        t_agent = time.time()
        trace.record("agent_call_start", {"request_id": request_id})
        reply, _new_history, is_hitl = await asyncio.wait_for(
            asyncio.to_thread(
                travel_engine.process_query,
                user_input=user_query,
                preference=preference,
                history=context_bundle.get("recent_messages_text", ""),
                memory=context_bundle.get("relevant_memory", ""),
                user_id=query.user_id,
                conversation_id=query.conversation_id,
                context_bundle=context_bundle,
                user_tier=quota_status.tier,
            ),
            timeout=145,
        )
        trace.record("agent_call_end", {"reply_preview": str(reply)[:200]}, latency_ms=(time.time() - t_agent) * 1000)

        t_proc = time.time()
        final_output = reply if is_hitl else clean_llm_output(process_llm_output(reply))
        trace.record("output_processed", {"final_reply_preview": str(final_output)[:200]}, latency_ms=(time.time() - t_proc) * 1000)

        t_save = time.time()
        add_message(query.user_id, query.conversation_id, "assistant", final_output)
        trace.record("db_assistant_message_saved", {}, latency_ms=(time.time() - t_save) * 1000)

        if not is_hitl:
            t_mem = time.time()
            durable_memory = _extract_durable_memory(user_query, final_output, trace)
            context_manager.store_memory(
                user_id=query.user_id,
                conversation_id=query.conversation_id,
                memory_text=durable_memory,
                tags=["travel", quota_status.tier],
                importance=1,
                trace=trace,
            )
            context_manager.prune_user_memories(query.user_id, trace=trace)
            trace.record("memory_processing_completed", {}, latency_ms=(time.time() - t_mem) * 1000)

        quota_service.commit_message_usage(query.user_id, request_id)
        quota_reserved = False
        trace.record("final_response", {
            "request_id": request_id,
            "answer_preview": str(final_output)[:300],
        }, latency_ms=(time.time() - t0) * 1000)

        return {"reply": final_output, "trace_id": request_id}

    except Exception as exc:
        if quota_reserved:
            quota_service.rollback_reservation(query.user_id, request_id)
        tb = traceback.format_exc()
        print(f"[query_controller] query workflow failed: {exc}\n{tb}")
        trace.record("query_error", {"error": str(exc), "traceback": tb}, latency_ms=(time.time() - t0) * 1000)
        return {
            "error": {
                "message": "Workflow failed during execution",
                "details": str(exc),
            },
            "trace_id": request_id,
        }
    finally:
        try:
            trace.save_to_redis(redis_client)
            trace.save_to_db()
        except Exception as trace_exc:
            print(f"Trace save failed: {trace_exc}")


async def query_helper_stream(query):
    result = await query_helper(query)
    if isinstance(result, dict) and "error" in result:
        yield f"data: {json.dumps(result)}\n\n"
        return
    reply_text = result.get("reply", "") if isinstance(result, dict) else ""
    for chunk in chunk_text(reply_text):
        yield f"data: {json.dumps({'type': 'chunk', 'content': chunk})}\n\n"
        await asyncio.sleep(0.005)
    yield f"data: {json.dumps({'final_reply': reply_text, 'trace_id': result.get('trace_id')})}\n\n"
