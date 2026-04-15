import json
import time
from backend.supabase_client.db_operations import (
      add_message, see_message, get_conversation_memory, update_conversation_memory,
      get_preference
      )
from llmops.token_tracker import TokenTracker
from service.cache_service import redis_client
from llmops.guardrails import *
from llmops.trace_service import ExecutionTrace
import uuid
import asyncio
from agent_file.agent.agentic_workflow import AgentRunner, TravelEngine
from llmops.model_router import ModelRouter
from agent_file.utils.config_loader import load_config
from agent_file.agent.agentic_workflow import AgentRunner


router = ModelRouter(load_config())
runner = AgentRunner(router)
travel_engine = TravelEngine(runner)

def fallback_to_json(raw_output: str):
    import re, json
    response = runner.fallback_json_agent(raw_input= raw_output)
    content = response.content if hasattr(response, 'content') else str(response)
    try:
        match = re.search(r'\{.*\}', content, re.DOTALL)
        if match:
            json_str = match.group()
            json_str = re.sub(r'\\\n', '', json_str)
            json_str = json_str.replace('\n', '\\n')
            parsed = json.loads(json_str)
            if 'reply' in parsed:
                return parsed
    except Exception:
        pass

    return {
        "reply": content,
        "preference": "",
        "confidence": 0
    }

def process_llm_output(raw_output: str):
    try:
        return validate_llm_output(raw_output)
    except Exception:
        # 🔥 fallback instead of crashing
        return fallback_to_json(raw_output)
    
token_tracker = TokenTracker(redis_client= redis_client)

import re

def clean_llm_output(text: str) -> str:
    # Remove anything that starts with <function=...>
    text = re.sub(r"<function=.*?>.*?</function>", "", text, flags=re.DOTALL)
    text = re.sub(r"<function=.*?>", "", text)

    # Clean up formatting
    text = re.sub(r"\n\s*\n", "\n\n", text)

    return text.strip()

async def query_helper(query):
    # ── Trace bootstrap ──────────────────────────────────────────────────────
    request_id = f"req_{uuid.uuid4().hex}"
    trace = ExecutionTrace(request_id=request_id)
    t0 = time.time()
    trace.record("query_start", {
        "request_id": request_id,
        "user_id": query.user_id,
        "conversation_id": query.conversation_id,
        "question_preview": query.question[:200]
    })

    try:
        # ── 1. Budget guard ───────────────────────────────────────────────────
        if not token_tracker.check_budget(user_id=query.user_id):
            trace.record("budget_exceeded", {"user_id": query.user_id})
            return {'message': 'Daily Limit Exceeded. Try again tomorrow.'}

        # ── 2. Guardrail / input sanitisation ─────────────────────────────────
        user_query, violation = sanitize_input(query.question)
        if violation:
            trace.record("guardrail_violation", {"question_preview": query.question[:200]})
            return {'message': 'Message violation detected'}

        trace.record("guardrail_pass", {"sanitised_preview": user_query[:200]})

        # ── 3. Persist user message ───────────────────────────────────────────
        t_db = time.time()
        add_message(
            user_id=query.user_id,
            conversation_id=query.conversation_id,
            role='user',
            content=user_query
        )
        trace.record("db_user_message_saved", {}, latency_ms=(time.time()-t_db)*1000)

        # ── 4. Fetch recent history ───────────────────────────────────────────
        t_hist = time.time()
        past_messages = see_message(query.conversation_id)
        history_str = ""
        for msg in past_messages[-8:]:
            history_str += f"{msg['role']}: {msg['content']}\n"
        trace.record("history_fetched", {
            "message_count": len(past_messages)
        }, latency_ms=(time.time()-t_hist)*1000)

        # ── 5. Fetch preference ────────────────────────────────────────────────
        t_pref = time.time()
        try:
            pref_data = get_preference(query.user_id)
            if isinstance(pref_data, list) and len(pref_data) > 0:
                preference = json.dumps({
                    "dietary": pref_data[0].get("dietary_preference"),
                    "custom": pref_data[0].get("custom_preference")
                })
            else:
                preference = ""
        except:
            preference = ""
        trace.record("preference_fetched", {
            "has_preference": bool(preference)
        }, latency_ms=(time.time()-t_pref)*1000)

        # ── 6. Fetch memory ───────────────────────────────────────────────────
        t_mem = time.time()
        try:
            memory = get_conversation_memory(query.conversation_id)
        except:
            memory = ""
        trace.record("memory_fetched", {
            "memory_length": len(memory or "")
        }, latency_ms=(time.time()-t_mem)*1000)

        # ── 7. Run agent ──────────────────────────────────────────────────────
        t_agent = time.time()
        trace.record("agent_call_start", {"request_id": request_id})

        reply, new_pref, new_history = await asyncio.wait_for(
            asyncio.to_thread(
                travel_engine.process_query,
                user_input=user_query,
                preference=preference,
                history=history_str,
                memory=memory,
                user_id=query.user_id
            ),
            timeout=30
        )

        trace.record("agent_call_end", {
            "reply_preview": str(reply)[:200]
        }, latency_ms=(time.time()-t_agent)*1000)

        # ── 8. Process / validate output ──────────────────────────────────────
        t_proc = time.time()
        reply = process_llm_output(reply)
        final_output = clean_llm_output(reply)
        trace.record("output_processed", {
            "final_reply_preview": str(final_output)[:200]
        }, latency_ms=(time.time()-t_proc)*1000)

        # ── 9. Persist assistant response ─────────────────────────────────────
        # Extract only the reply text — we do NOT store the full dict in the DB.
        # Storing a dict would cause Pydantic errors when /see_message tries to read it back.
        t_save = time.time()
        reply_text = final_output
        add_message(
            user_id=query.user_id,
            conversation_id=query.conversation_id,
            role='assistant',
            content=reply_text  # Always a plain string
        )
        trace.record("db_assistant_message_saved", {}, latency_ms=(time.time()-t_save)*1000)

        # ── 10. Update memory ─────────────────────────────────────────────────
        try:
            t_mupd = time.time()
            updated_memory = f"{memory}\nUser: {user_query}\nAssistant: {final_output}"
            updated_memory = updated_memory[-2000:]   # prevent explosion
            update_conversation_memory(query.conversation_id, updated_memory)
            trace.record("memory_updated", {}, latency_ms=(time.time()-t_mupd)*1000)
        except Exception as e:
            trace.record("memory_update_failed", {"error": str(e)})
            print("Memory update failed:", e)

        # ── 11. Final controller response trace ───────────────────────────────
        trace.record("final_response", {
            "request_id": request_id,
            "answer_preview": str(final_output)
        }, latency_ms=(time.time()-t0)*1000)

        # Return just the reply string — the frontend reads data.reply
        return {"reply": reply_text}

    except Exception as e:
        trace.record("query_error", {
            "error": str(e)
        }, latency_ms=(time.time()-t0)*1000)
        raise e

    finally:
        # Always persist trace regardless of success / failure
        try:
            trace.save_to_redis(redis_client)
            trace.save_to_db()
        except Exception as te:
            print(f"Trace save failed: {te}")